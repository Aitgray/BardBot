import logging
import discord
from discord.ext import commands, voice_recv
import os
import json
import time
import io
from pydub import AudioSegment
from vector_db import VectorDB
import requests
import whisper
from dataclasses import dataclass
from typing import Dict, List, Optional
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import torch
import asyncio

# Load configuration from config.json
def load_config():
    with open('config.json', 'r') as f: # No error handling for missing config
        return json.load(f)

config = load_config()

DISCORD_BOT_TOKEN = config["DISCORD_BOT_TOKEN"]

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Enable voice state intents

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------
# Whisper multiprocessing pool
# ---------------------------

_WORKER_MODEL = None
_WORKER_DEVICE = None

def _whisper_worker_init(model_name: str):
    """Initializer for each worker process: load Whisper once per worker."""
    global _WORKER_MODEL, _WORKER_DEVICE

    _WORKER_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    _WORKER_MODEL = whisper.load_model(model_name, device=_WORKER_DEVICE)

def _whisper_worker_transcribe(args):
    """Worker task: transcribe a single WAV path."""
    user_id, wav_path = args

    fp16 = torch.cuda.is_available()
    result = _WORKER_MODEL.transcribe(
        wav_path,
        language="en",
        fp16=fp16,
        verbose=False
    )
    text = (result.get("text") or "").strip()
    return user_id, wav_path, text

@dataclass
class AudioChunk:
    user_id: int
    chunk_index: int
    pcm: bytes
    t_start: float
    t_end: float

class TranscriptionSink(voice_recv.BasicSink):
    """
    Buffers incoming PCM per-user, slices it into rolling windows (with overlap),
    and transcribes the resulting chunks on flush.

    This avoids huge per-user WAVs and produces timestamped transcript segments.
    """

    # Discord voice recv in your code: 48kHz, 16-bit, stereo
    SAMPLE_RATE = 48000
    CHANNELS = 2
    SAMPLE_WIDTH = 2  # bytes per sample per channel

    def __init__(
        self,
        *,
        whisper_model_name: str = "small.en",
        window_seconds: float = 30.0,
        overlap_seconds: float = 5.0,
        min_flush_seconds: float = 3.0,
    ):
        super().__init__(self.process_audio)

        # Keep: name only (workers load the model later)
        self.whisper_model_name = whisper_model_name

        # Keep: windowing configuration
        self.window_seconds = float(window_seconds)
        self.overlap_seconds = float(overlap_seconds)
        self.min_flush_seconds = float(min_flush_seconds)

        self._bytes_per_second = self.SAMPLE_RATE * self.CHANNELS * self.SAMPLE_WIDTH
        self._window_bytes = int(self._bytes_per_second * self.window_seconds)
        self._overlap_bytes = int(self._bytes_per_second * self.overlap_seconds)
        self._min_flush_bytes = int(self._bytes_per_second * self.min_flush_seconds)

        # Recording gate + raw buffers (full session per user)
        self.recording = False
        self.audio_data: Dict[int, io.BytesIO] = {}

        # Keep: buffers + chunk tracking
        self._buffers: Dict[int, bytearray] = {}
        self._chunk_counts: Dict[int, int] = {}
        self._emitted: List[AudioChunk] = []

        # Keep: timing
        self.session_start_ts: Optional[float] = None


    def set_session_start(self, ts: float) -> None:
        self.session_start_ts = ts

    def start_recording(self) -> None:
        self.recording = True
        self.audio_data = {}
        self._buffers = {}
        self._chunk_counts = {}
        self._emitted = []

    def stop_recording(self) -> None:
        self.recording = False

    def _duration_seconds(self, n_bytes: int) -> float:
        return n_bytes / float(self._bytes_per_second)

    def process_audio(self, user, data: voice_recv.VoiceData):
        """
        Called by the voice receive client frequently. Must be fast and non-blocking.
        """
        if not self.recording:
            return

        buf_io = self.audio_data.get(user.id)
        if buf_io is None:
            buf_io = io.BytesIO()
            self.audio_data[user.id] = buf_io
        buf_io.write(data.pcm)

        try:
            uid = user.id
            buf = self._buffers.setdefault(uid, bytearray())
            buf.extend(data.pcm)

            # Emit chunks while we have at least one full window
            while len(buf) >= self._window_bytes:
                idx = self._chunk_counts.get(uid, 0) + 1
                self._chunk_counts[uid] = idx

                chunk_pcm = bytes(buf[:self._window_bytes])

                # Compute approximate timestamps based on cumulative audio emitted per user
                # (This is not perfect diarization timing, but it's consistent and useful.)
                if self.session_start_ts is None:
                    base = time.time()
                else:
                    base = self.session_start_ts

                # Total seconds emitted for this user before this chunk:
                emitted_seconds = (idx - 1) * (self.window_seconds - self.overlap_seconds)
                t_start = base + emitted_seconds
                t_end = t_start + self.window_seconds

                self._emitted.append(AudioChunk(
                    user_id=uid,
                    chunk_index=idx,
                    pcm=chunk_pcm,
                    t_start=t_start,
                    t_end=t_end
                ))

                # Keep overlap + any remaining tail in buffer
                keep_from = max(0, self._window_bytes - self._overlap_bytes)
                buf[:] = buf[keep_from:]
        except Exception as e:
            logging.error(f"Error processing audio for user {user}: {e}")

    def flush_and_transcribe(self, session_dir: str) -> list[dict]: # The whisper model is always loaded into the main process, causing the entire event loop to get blocked while the model loads/trascribes
        segments: list[dict] = []

        recordings_dir = os.path.join(session_dir, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)

        now = time.time()
        seg_id = 1

        # 1) Export WAVs first (fast)
        jobs = []
        for user_id, buf in self.audio_data.items(): # 
            pcm = buf.getvalue()
            if not pcm:
                continue

            audio_segment = AudioSegment.from_raw(
                io.BytesIO(pcm),
                sample_width=2,
                frame_rate=48000,
                channels=2
            )

            wav_path = os.path.join(recordings_dir, f"{user_id}.wav")
            audio_segment.export(wav_path, format="wav")
            jobs.append((user_id, wav_path))

        # Clear buffers early to free memory
        self.audio_data = {}

        if not jobs:
            return []

        # 2) Decide worker count
        model_vram_gb = float(config.get("WHISPER_MODEL_VRAM_GB", 2.0))  # your estimate
        vram_fraction = float(config.get("WHISPER_VRAM_FRACTION", 0.50))  # e.g., 0.5 uses 50% VRAM
        max_workers_cfg = int(config.get("WHISPER_MAX_WORKERS", 0))  # 0 = auto

        workers = 1
        if torch.cuda.is_available():
            total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            auto_workers = max(1, int(math.floor((total_vram_gb * vram_fraction) / model_vram_gb)))
            workers = auto_workers
        else:
            workers = 1  # CPU mode: do not parallelize by default

        if max_workers_cfg > 0:
            workers = min(workers, max_workers_cfg)

        workers = min(workers, len(jobs))  # never more workers than jobs

        logging.info("Whisper transcription: jobs=%d workers=%d cuda=%s",
                    len(jobs), workers, torch.cuda.is_available())

        # 3) Transcribe in parallel (one model per worker)
        # Use spawn context for CUDA safety.
        ctx = mp.get_context("spawn")

        if workers == 1:
            # Single-worker fallback (still uses worker initializer to keep behavior identical)
            _whisper_worker_init(self.whisper_model_name)
            for user_id, wav_path in jobs:
                user_id, wav_path, text = _whisper_worker_transcribe((user_id, wav_path))
                if not text:
                    continue
                segments.append({
                    "session_id": None,
                    "segment_id": seg_id,
                    "speaker_label": str(user_id),
                    "t_start": now, # Both start and end are set to now which needs to be fixed.
                    "t_end": now,
                    "text": text,
                    "audio_path": wav_path
                })
                seg_id += 1
            return segments

        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=ctx,
            initializer=_whisper_worker_init,
            initargs=(self.whisper_model_name,),
        ) as ex:
            futures = [ex.submit(_whisper_worker_transcribe, job) for job in jobs]

            for fut in as_completed(futures):
                user_id, wav_path, text = fut.result()
                if not text:
                    continue
                segments.append({
                    "session_id": None,
                    "segment_id": seg_id,
                    "speaker_label": str(user_id),
                    "t_start": now,
                    "t_end": now,
                    "text": text,
                    "audio_path": wav_path
                })
                seg_id += 1

        return segments

class VoiceRecorder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_client = None
        self.recording = False
        self.session_id = None
        self.session_start_ts = None
        self.transcripts = []
        self.sink: TranscriptionSink | None = None

    @commands.command() # This didn't work this session, need to investigate why
    async def join(self, ctx):
        if self.voice_client and self.voice_client.is_connected():
            await ctx.send("Already connected to a voice channel.")
            return
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You must be in a voice channel first.")
            return

        try: # Perhaps I can split this onto a seperate thread, and have it write every time it performs a transcription.
            self.voice_client = await ctx.author.voice.channel.connect(
                cls=voice_recv.VoiceRecvClient,
                reconnect=False    
            )
            model_name = config.get("WHISPER_MODEL", "small.en")

            self.sink = TranscriptionSink(
                whisper_model_name=model_name,
                window_seconds=config.get("CHUNK_WINDOW_SECONDS", 30.0),
                overlap_seconds=config.get("CHUNK_OVERLAP_SECONDS", 5.0),
                min_flush_seconds=config.get("CHUNK_MIN_FLUSH_SECONDS", 3.0),
            )
            self.voice_client.listen(self.sink)
            await ctx.send("Connected and listening. Use !start_recording to begin.")
        except Exception as e:
            await ctx.send(f"Failed to connect: {e}")

    @commands.command()
    async def leave(self, ctx):
        print("Leave command invoked")
        await ctx.send("Leave command invoked")
        if self.voice_client:
            if self.recording:
                await self.stop_recording(ctx)
            await self.voice_client.disconnect()
            self.voice_client = None
            print("Disconnected from the voice channel.")
            await ctx.send("Disconnected from the voice channel.")
        else:
            print("Not connected to any voice channel.")
            await ctx.send("Not connected to any voice channel.")

    @commands.command()
    async def start_recording(self, ctx):
        if not self.voice_client or not self.voice_client.is_connected():
            await ctx.send("Not connected. Use !join first.")
            return
        if not self.sink:
            await ctx.send("No sink available; reconnect with !join.")
            return

        self.session_id = time.strftime("%Y%m%d-%H%M%S")
        self.session_start_ts = time.time()
        self.sink.set_session_start(self.session_start_ts)
        self.sink.start_recording()

        self.recording = True
        self.transcripts = []
        await ctx.send(f"Started recording. Session: {self.session_id}")

    @commands.command()
    async def stop_recording(self, ctx):
        if not self.recording:
            await ctx.send("Not currently recording.")
            return

        self.recording = False
        if self.sink:
            self.sink.stop_recording()
        await self.write_transcription_offline()
        await ctx.send("Stopped recording and saved transcript.")

    async def write_transcription_offline(self):
        if not self.session_id:
            return
        
        if not self.sink:
            print("No sink available; are you connected and listening?")
            return

        session_dir = os.path.join("sessions", self.session_id)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)

        transcript_path = os.path.join(session_dir, "turns.jsonl")
        
        loop = asyncio.get_running_loop()
        segments = await loop.run_in_executor(
            None,
            self.sink.flush_and_transcribe,
            session_dir
        )

        for seg in segments:
            seg["session_id"] = self.session_id

        if not segments:
            print("No transcribed segments produced.")
            return

        with open(transcript_path, 'w', encoding="utf-8") as f:
            for segment in segments:
                f.write(json.dumps(segment) + "\n")

        self.transcripts = segments
        print(f"Saved transcript to {transcript_path}")

    @commands.command()
    async def summarize(self, ctx):
        await ctx.send("Summarizing transcript... this may take a moment.")

        vector_db = VectorDB() # The vecotr database is recreated every time every single time we perform summarization.

        # Indexing: ideally, index obsidian once at startup, but leaving as-is for now
        # Right now Obsidian won't be indexed b/c I'm running in a docker container and the notes aren't copied over.
        # In the future I may want to add the Obsidian notes to a volume, if I get the notes to sync with github maybe I can pull any updates on startup?
        # That way I could also theoretically push all the summaries that are generated to my Vault automatically
        vector_db.index_transcripts()
        obsidian_vault_path = config.get("OBSIDIAN_VAULT_PATH")
        if obsidian_vault_path:
            vector_db.index_obsidian_vault(obsidian_vault_path)
        else:
            await ctx.send("Obsidian vault path not configured. Skipping Obsidian context.")

        if not self.transcripts:
            await ctx.send("No transcript to summarize.")
            return

        consolidated_transcript = ""
        for segment in self.transcripts:
            consolidated_transcript += f"User {segment['speaker_label']}: {segment['text']}\n"

        # Retrieve only top-k notes
        top_k = int(config.get("RAG_TOP_K", 4))
        score_threshold = config.get("RAG_SCORE_THRESHOLD")  # optional; may be None

        search_results = vector_db.search(consolidated_transcript)

        # Enforce top-k early
        search_results = search_results[:top_k]

        relevant_notes_parts = []
        for hit in search_results:
            # Optional score filtering if your VectorDB hits provide .score
            if score_threshold is not None and hasattr(hit, "score"):
                if hit.score < float(score_threshold):
                    continue

            payload = getattr(hit, "payload", None) or {}
            if payload.get("source") and payload.get("text"):
                relevant_notes_parts.append(payload["text"])

        relevant_notes = "\n\n".join(relevant_notes_parts)

        prompt = f"""You are an assistant that summarizes Discord call transcripts.
    Use the provided context if relevant. If context is irrelevant, ignore it.

    Context (top {top_k} retrieved notes):
    {relevant_notes}

    Transcript:
    {consolidated_transcript}

    Write:
    - A concise summary in markdown
    - Decisions (if any)
    - Action items with owners (if any)
    """

        await ctx.send("Sending prompt for local LLM")
        try:
            payload = {
                "model": "llama3.1:8b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    # "num_ctx": 8192 Getting rid of this for now, eventually the transcript needs to be partitioned into chunks but for now I'm just going to send the whole thing
                }
            }

            response = requests.post(
                "http://ollama:11434/api/generate", 
                json=payload,
                timeout=180,
            )
            if response.status_code == 200:
                summary = response.json()["response"]
                await ctx.send("Summary successfully generated!")
            else:
                summary = f"Error: Could not get summary from local LLM. Status code: {response.status_code}"
        except requests.exceptions.RequestException as e:
            summary = f"Error: Could not connect to local LLM: {e}"
        await ctx.send(f"**Summary:**\n{summary}")
        # I'd love it if the session number was automatically printed as well. 
        # await self.post_summary(ctx, summary)

    async def post_summary(self, ctx, summary):
        """
        Posts the summary to a specific Discord channel.
        This is a placeholder for the actual implementation.
        """
        channel_id = config.get("SUMMARY_CHANNEL_ID")
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"**Session Summary:**\n\n{summary}")
            else:
                await ctx.send("Summary channel not found.")
        else:
            await ctx.send("No summary channel configured.")

    @commands.command()
    async def read_summary(self, ctx):
        """
        Reads the most recent summary aloud using a local TTS engine.
        This is a placeholder for the actual implementation.
        """
        # --- PSEUDOCODE FOR LOCAL TTS AND PLAYBACK ---
        # 1. Find and read the most recent summary file.
        #    - This assumes the summary is saved to 'transcripts/summary.txt'.
        #
        # try:
        #     with open("transcripts/summary.txt", "r") as f:
        #         summary_text = f.read()
        # except FileNotFoundError:
        #     await ctx.send("No summary file found.")
        #     return
        #
        # 2. Send the summary text to a local TTS API.
        #    - This assumes you have a local TTS engine running with an API endpoint (e.g., http://localhost:8081/tts).
        #    - The API should return an audio file (e.g., wav, mp3).
        #
        # import requests
        # try:
        #     response = requests.post("http://localhost:8081/tts", json={"text": summary_text})
        #     if response.status_code == 200:
        #         with open("summary.wav", "wb") as f:
        #             f.write(response.content)
        #     else:
        #         await ctx.send("Error: Could not generate audio from local TTS.")
        #         return
        # except requests.exceptions.RequestException as e:
        #     await ctx.send(f"Error: Could not connect to local TTS: {e}")
        #     return
        #
        # 3. Play the generated audio file in the voice channel.
        #    - You need to be connected to a voice channel for this to work.
        #
        # if self.voice_client and self.voice_client.is_connected():
        #     audio_source = discord.FFmpegPCMAudio("summary.wav")
        #     if not self.voice_client.is_playing():
        #         self.voice_client.play(audio_source, after=lambda e: print(f'Player error: {e}') if e else None)
        #         await ctx.send("Reading summary...")
        #     else:
        #         await ctx.send("Already playing audio.")
        # else:
        #     await ctx.send("Not connected to a voice channel.")
        # --- END PSEUDOCODE ---

        await ctx.send("This is a placeholder for reading the summary aloud.")


    @commands.command()
    async def stop(self, ctx):  # Shutdown the bot
        await ctx.send("Shutting down the bot.")
        await self.bot.close()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('------')

async def main():
    # Create sessions directory if it doesn't exist
    if not os.path.exists("sessions"):
        os.makedirs("sessions")

    async with bot:
        await bot.add_cog(VoiceRecorder(bot))
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
