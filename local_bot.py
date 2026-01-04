
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
    def __init__(self, callback):
        super().__init__(self.process_audio)
        self.callback = callback
        self.recognizer = sr.Recognizer()
        self.audio_data = {}

    def process_audio(self, user, data: voice_recv.VoiceData):
        if user.id not in self.audio_data:
            self.audio_data[user.id] = io.BytesIO()
        self.audio_data[user.id].write(data.pcm)

        # Process the audio in a separate thread to avoid blocking
        threading.Thread(target=self.transcribe_chunk, args=(user.id, data.pcm)).start()

    def transcribe_chunk(self, user_id, pcm_data):
        audio_segment = AudioSegment.from_raw(
            io.BytesIO(pcm_data),
            sample_width=2,
            frame_rate=48000,
            channels=2
        )
        # Export as a temporary wav file in memory
        wav_io = io.BytesIO()
        audio_segment.export(wav_io, format="wav")
        wav_io.seek(0)

        with sr.AudioFile(wav_io) as source:
            audio = self.recognizer.record(source)
            try:
                # Using recognize_whisper for local transcription
                # This may require a local model to be available
                text = self.recognizer.recognize_whisper(audio, language="english")
                if text:
                    self.callback(user_id, text)
            except sr.UnknownValueError:
                pass  # Ignore if speech is not understood
            except sr.RequestError as e:
                print(f"Could not request results from Whisper; {e}")

class VoiceRecorder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_client = None
        self.recording = False
        self.session_id = None
        self.transcripts = []

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
        print("Join command invoked")
        await ctx.send("Join command invoked")
        if ctx.author.voice:
            print(f"Author is in a voice channel: {ctx.author.voice.channel.name}")
            await ctx.send(f"Author is in a voice channel: {ctx.author.voice.channel.name}")
            try:
                self.voice_client = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
                self.voice_client.listen(TranscriptionSink(self.transcription_callback))
                print("Connected to the voice channel and listening for transcriptions.")
                await ctx.send("Connected to the voice channel and listening for transcriptions.")
            except Exception as e:
                print(f"Failed to connect to the voice channel: {e}")
                await ctx.send(f"Failed to connect to the voice channel: {e}")
        else:
            print("Author is not in a voice channel")
            await ctx.send("You are not in a voice channel.")

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
        print("Start recording command invoked")
        await ctx.send("Start recording command invoked")
        self.session_id = time.strftime("%Y%m%d-%H%M%S")
        self.recording = True
        self.transcripts = []
        await ctx.send("Started recording.")

    @commands.command()
    async def stop_recording(self, ctx):
        print("Stop recording command invoked")
        await ctx.send("Stop recording command invoked")
        self.recording = False
        await self.write_transcription()
        await ctx.send("Stopped recording and saved transcript.")

    async def write_transcription(self):
        if not self.transcripts:
            return

        session_dir = os.path.join("sessions", self.session_id)
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)

        transcript_path = os.path.join(session_dir, "turns.jsonl")
        with open(transcript_path, 'w') as f:
            for segment in self.transcripts:
                f.write(json.dumps(segment) + '\n')
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
        vector_db.index_transcripts()
        obsidian_vault_path = config.get("OBSIDIAN_VAULT_PATH")
        if obsidian_vault_path:
            vector_db.index_obsidian_vault(obsidian_vault_path)
        else:
            await ctx.send("Obsidian vault path not configured. Skipping Obsidian context.")

        # 3. Consolidate current session's transcript
        if not self.transcripts:
            await ctx.send("No transcript to summarize.")
            return

        consolidated_transcript = ""
        for segment in self.transcripts:
            consolidated_transcript += f"User {segment['speaker_label']}: {segment['text']}\n"

        # 4. Retrieve relevant notes from Obsidian vault
        search_results = vector_db.search(consolidated_transcript)
        relevant_notes = ""
        for hit in search_results:
            if hit.payload.get('source'):
                relevant_notes += hit.payload['text'] + "\n\n"

        # 5. Construct prompt for local LLM
        context = f"""Relevant Notes from Obsidian:\n{relevant_notes}\n\n"""
        prompt = f"""Using the following context, please summarize the transcript.\n\nContext:\n{context}\n\nTranscript:\n{consolidated_transcript}"""

        # 6. Send prompt to local LLM API
        try:
            response = requests.post("http://localhost:8080/summarize", json={"text": prompt})
            if response.status_code == 200:
                summary = response.json()["summary"]
            else:
                summary = f"Error: Could not get summary from local LLM. Status code: {response.status_code}"
        except requests.exceptions.RequestException as e:
            summary = f"Error: Could not connect to local LLM: {e}"

        await ctx.send(f"**Summary:**\n{summary}")
        await self.post_summary(ctx, summary)


    async def post_summary(self, ctx, summary):
        """
        Posts the summary to a specific Discord channel.
        This is a placeholder for the actual implementation.
        """
        # --- PSEUDOCODE FOR DISCORD POSTING ---
        # 1. Get the channel object where you want to post the summary.
        #    - You could get the channel ID from your config file.
        #    - Or, you could have a command that sets the channel.
        #
        # channel_id = config.get("SUMMARY_CHANNEL_ID")
        # if channel_id:
        #     channel = self.bot.get_channel(channel_id)
        #     if channel:
        #         await channel.send(f"**Meeting Summary:**\n\n{summary}")
        #     else:
        #         await ctx.send("Summary channel not found.")
        # else:
        #     await ctx.send("No summary channel configured.")
        # --- END PSEUDOCODE ---

        await ctx.send("This is a placeholder for posting the summary to a channel.")

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
