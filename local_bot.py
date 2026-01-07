import logging
import discord
from discord.ext import commands, voice_recv
import os
import json
import time
import speech_recognition as sr
import io
import threading
from pydub import AudioSegment
from vector_db import VectorDB
import requests
import whisper
from dataclasses import dataclass
from typing import Dict, List, Optional

# Load configuration from config.json
def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()

DISCORD_BOT_TOKEN = config["DISCORD_BOT_TOKEN"]

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Enable voice state intents

bot = commands.Bot(command_prefix="!", intents=intents)

class TranscriptionSink(voice_recv.BasicSink):
    def __init__(self, callback, *, whisper_model_name: str = "small.en"):
        super().__init__(self.process_audio)
        self.callback = callback
        self.audio_data: dict[int, io.BytesIO] = {}
        self.whisper_model_name = whisper_model_name
        self.whisper_model = whisper.load_model(self.whisper_model_name, device="cuda")

    def process_audio(self, user, data: voice_recv.VoiceData):
        if user.id not in self.audio_data:
            self.audio_data[user.id] = io.BytesIO()
        self.audio_data[user.id].write(data.pcm)

    def flush_and_transcribe(self, session_dir: str) -> list[dict]:
        segments: list[dict] = []

        recordings_dir = os.path.join(session_dir, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)

        now = time.time()
        seg_id = 1
        for user_id, buf in self.audio_data.items():
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

            result = self.whisper_model.transcribe(
                wav_path,
                language="en",
                fp16=True,
                verbose=False
            )
            text = (result.get("text") or "").strip()
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

        self.audio_data = {}
        return segments

class VoiceRecorder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_client = None
        self.recording = False
        self.session_id = None
        self.transcripts = []
        self.sink: TranscriptionSink | None = None

    def transcription_callback(self, user_id, text):
        if self.recording:
            timestamp = time.time()
            segment = {
                "session_id": self.session_id,
                "segment_id": len(self.transcripts) + 1,
                "speaker_label": str(user_id),
                "t_start": timestamp,
                "t_end": timestamp, # Note: This is a simplification. For more accurate t_end, we would need more sophisticated logic.
                "text": text,
            }
            self.transcripts.append(segment)
            print(f"User {user_id}: {text}")

    @commands.command()
    async def join(self, ctx):
        await ctx.send(f"Author is in a voice channel: {ctx.author.voice.channel.name}")
        try:
            self.voice_client = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
            # Initialize sink once per connection.
            # Uses local Whisper small.en; no per-chunk recognize_whisper() calls.
            model_name = config.get("WHISPER_MODEL", "small.en")
            self.sink = TranscriptionSink(self.transcription_callback, whisper_model_name=model_name)
            self.voice_client.listen(self.sink)
            print("Connected to the voice channel and listening for transcriptions.")
            await ctx.send("Connected to the voice channel and listening for transcriptions.")
        except Exception as e:
            print(f"Failed to connect to the voice channel: {e}")
            await ctx.send(f"Failed to connect to the voice channel: {e}")
        await ctx.send("Start recording command invoked")
        self.session_id = time.strftime("%Y%m%d-%H%M%S")
        self.recording = True
        self.transcripts = []
        await ctx.send("Started recording.")

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
    async def start_recording(self, ctx): # I believe this is depreciated now
        print("Start recording command invoked")
        await ctx.send("Start recording command invoked")
        self.session_id = time.strftime("%Y%m%d-%H%M%S")
        self.recording = True
        self.transcripts = []
        await ctx.send("Started recording.")

    @commands.command()
    async def stop_recording(self, ctx):
        print("Stop recording command invoked!")
        await ctx.send("Stop recording command invoked!")
        self.recording = False
        print("Writing transcription")
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
        """
        Summarizes the transcriptions using a local LLM with RAG.
        """
        await ctx.send("Summarizing transcript... this may take a moment.")

        # 1. Initialize VectorDB
        vector_db = VectorDB()

        # 2. Index transcripts and Obsidian vault
        await ctx.send("Indexing transcripts.")
        vector_db.index_transcripts()
        obsidian_vault_path = config.get("OBSIDIAN_VAULT_PATH")
        if obsidian_vault_path:
            vector_db.index_obsidian_vault(obsidian_vault_path) #
        else:
            await ctx.send("Obsidian vault path not configured. Skipping Obsidian context.") # The path for the vault is not currently being found. This is prob b/c it doesn't exist within the docker container.

        # 3. Consolidate current session's transcript
        await ctx.send("Consolidating transcripts.")
        if not self.transcripts:
            await ctx.send("No transcript to summarize.")
            return

        consolidated_transcript = ""
        for segment in self.transcripts:
            consolidated_transcript += f"User {segment['speaker_label']}: {segment['text']}\n"

        # 4. Retrieve relevant notes from Obsidian vault
        await ctx.send("Retrieving relevant notes...")
        try:
            query_text = consolidated_transcript[-6000:]
            search_results = await asyncio.wait_for(
                asyncio.to_thread(vector_db.search, query_text, 10),
                timeout=30.0,
            )
        except Exception as e:
            # This is the part you’re missing right now; you’re likely hitting here.
            await ctx.send(f"RAG retrieval failed: {type(e).__name__}: {e}")
            raise  # also re-raise so it shows in docker logs

        relevant_notes = ""
        await ctx.send(f"Num search results: {len(search_results)}")
        for hit in search_results: # We should only grab the top couple results, not all of them. 
            if hit.payload.get('source'):
                relevant_notes += hit.payload['text'] + "\n\n"

        # 5. Construct prompt for local LLM, still need to implement chunking.
        await ctx.send("Constructing prompt for local LLM.")
        context = f"""Relevant Notes from Obsidian:\n{relevant_notes}\n\n"""
        prompt = f"""Using the following context, please summarize the transcript.\n\nContext:\n{context}\n\nTranscript:\n{consolidated_transcript}"""

        # 6. Send prompt to local LLM API
        await ctx.send("Sending prompt to local LLM.")
        try:
            payload = {
                "model": "llama3.1:8b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 8192
                }
            }

            resp = requests.post(
                "http://ollama:11434/api/generate",
                json=payload,
                timeout=180,
            )
            resp.raise_for_status()

            data = resp.json()
            summary = data.get("response", "").strip()
            if not summary:
                summary = "Error: LLM returned an empty response."

        except requests.exceptions.RequestException as e:
            summary = f"Error: Could not connect to local LLM: {e}"
        except ValueError as e:
            summary = f"Error: Could not parse LLM JSON response: {e}"

        await ctx.send(f"**Summary:**\n{summary}") # Will remove this once I know that the post summary function works.
        await self.post_summary(ctx, summary)

    async def post_summary(self, ctx, summary):
        """
        Posts the summary to a specific Discord channel.
        This is a placeholder for the actual implementation.
        """
        channel_id = config.get("SUMMARY_CHANNEL_ID")
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(f"**Meeting Summary:**\n\n{summary}")
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
    import asyncio
    asyncio.run(main())
