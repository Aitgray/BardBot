
import logging
import discord
from discord.ext import commands, voice_recv
import os
import wave
import asyncio
import json
import time
from local_transcription import transcribe_audio

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

class VoiceRecorder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recording = False
        self.voice_client = None
        self.audio_data = {}
        self.channels = 2  # Number of audio channels (Discord typically uses stereo audio)
        self.sample_width = 2  # Number of bytes per sample (16-bit audio)
        self.frame_rate = 48000  # Sample rate (48 kHz)
        self.recording_task = None

    @commands.command()
    async def join(self, ctx):
        print("Join command invoked")
        await ctx.send("Join command invoked")
        if ctx.author.voice:
            print(f"Author is in a voice channel: {ctx.author.voice.channel.name}")
            await ctx.send(f"Author is in a voice channel: {ctx.author.voice.channel.name}")
            try:
                self.voice_client = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
                self.voice_client.listen(voice_recv.BasicSink(self.callback))
                print("Connected to the voice channel.")
                await ctx.send("Connected to the voice channel.")
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
        self.recording = True
        self.audio_data = {}

        # Start a task to reset recording every 10 minutes
        self.recording_task = asyncio.create_task(self.reset_recording_periodically(ctx))
        await ctx.send("Started recording")

    @commands.command()
    async def stop_recording(self, ctx):
        print("Stop recording command invoked")
        await ctx.send("Stop recording command invoked")
        self.recording = False
        if self.recording_task:
            self.recording_task.cancel()  # Cancel the periodic reset task
        await self.save_audio(ctx)
        await ctx.send("Stopped recording")

    async def reset_recording_periodically(self, ctx):
        try:
            while self.recording:
                await asyncio.sleep(600)  # 10 minutes
                await self.save_audio(ctx)
                self.audio_data = {}  # Reset audio data for the next recording period
                await ctx.send("Recording period reset. Continuing recording...")
        except asyncio.CancelledError:
            pass

    def callback(self, user, data: voice_recv.VoiceData):
        if self.recording:
            if user.id not in self.audio_data:
                self.audio_data[user.id] = []
            self.audio_data[user.id].append(data.pcm)

    async def save_audio(self, ctx):
        for user_id, audio_chunks in self.audio_data.items():
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f'{timestamp}_{user_id}.wav'
            filepath = os.path.join("recordings", filename)
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.sample_width)
                wf.setframerate(self.frame_rate)
                wf.writeframes(b''.join(audio_chunks))
            await ctx.send(f"Saved audio to {filename}")

            # Transcribe the audio file
            transcription = transcribe_audio(filepath)
            transcript_filename = f'{timestamp}_{user_id}.txt'
            transcript_filepath = os.path.join("transcripts", transcript_filename)
            with open(transcript_filepath, "w") as f:
                f.write(transcription)
            await ctx.send(f"Transcription for {filename} saved to {transcript_filename}")

            # --- PSEUDOCODE FOR SQLITE INTEGRATION ---
            # 1. Connect to the SQLite database.
            #    - The database file will be created if it doesn't exist.
            #
            # import sqlite3
            # conn = sqlite3.connect('transcripts.db')
            # cursor = conn.cursor()
            #
            # 2. Create a table to store transcripts if it doesn't exist.
            #
            # cursor.execute('''
            #     CREATE TABLE IF NOT EXISTS transcripts (
            #         id INTEGER PRIMARY KEY AUTOINCREMENT,
            #         user_id TEXT NOT NULL,
            #         timestamp TEXT NOT NULL,
            #         transcription_text TEXT NOT NULL
            #     )
            # ''')
            #
            # 3. Insert the new transcription into the table.
            #
            # cursor.execute("INSERT INTO transcripts (user_id, timestamp, transcription_text) VALUES (?, ?, ?)",
            #                (user_id, timestamp, transcription))
            # conn.commit()
            # conn.close()
            # --- END PSEUDOCODE ---

    @commands.command()
    async def summarize(self, ctx):
        """
        Summarizes the transcriptions using a local LLM.
        This is a placeholder for the actual implementation.
        """
        # --- PSEUDOCODE FOR LOCAL LLM SUMMARIZATION WITH RAG ---
        # 1. Consolidate the current session's transcript files into one text block.
        #
        # consolidated_transcript = ""
        # for filename in os.listdir("transcripts"):
        #     if filename.endswith(".txt"):
        #         user_id = filename.split('_')[1]
        #         with open(os.path.join("transcripts", filename), "r") as f:
        #             consolidated_transcript += f"User {user_id}:\n{f.read()}\n\n"
        #
        # 2. Retrieve relevant notes from Obsidian vault.
        #    - You would need to specify the path to your Obsidian vault.
        #    - You could search for files with keywords from the current transcript.
        #
        # import os
        # obsidian_vault_path = "/path/to/your/obsidian/vault"
        # relevant_notes = ""
        # for root, dirs, files in os.walk(obsidian_vault_path):
        #     for file in files:
        #         if file.endswith(".md"):
        #             # Add logic here to determine if the note is relevant
        #             # For example, by searching for keywords from the transcript.
        #             with open(os.path.join(root, file), "r") as f:
        #                 relevant_notes += f.read() + "\n\n"
        #
        # 3. Retrieve previous summaries.
        #    - You could read summary files from a directory.
        #    - Or, you could query the SQLite database for past session data.
        #
        # previous_summaries = ""
        # # Logic to retrieve past summaries
        #
        # 4. Combine the context (notes, past summaries) and the current transcript.
        #
        # context = f"""Relevant Notes:\n{relevant_notes}\n\nPrevious Summaries:\n{previous_summaries}"""
        # prompt = f"""Using the following context, please summarize the transcript.\n\nContext:\n{context}\n\nTranscript:\n{consolidated_transcript}"""
        #
        # 5. Send the combined prompt to a local LLM API.
        #
        # import requests
        # try:
        #     response = requests.post("http://localhost:8080/summarize", json={"text": prompt})
        #     if response.status_code == 200:
        #         summary = response.json()["summary"]
        #     else:
        #         summary = "Error: Could not get summary from local LLM."
        # except requests.exceptions.RequestException as e:
        #     summary = f"Error: Could not connect to local LLM: {e}"
        #
        # 6. The `summary` variable would now hold the summarized text.
        #    - You should also save this summary for future RAG context.
        # --- END PSEUDOCODE ---

        summary = "This is a placeholder summary. Implement the pseudocode to generate a real summary."
        await ctx.send(summary)
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
    # Create recordings and transcripts directories if they don't exist
    if not os.path.exists("recordings"):
        os.makedirs("recordings")
    if not os.path.exists("transcripts"):
        os.makedirs("transcripts")

    async with bot:
        await bot.add_cog(VoiceRecorder(bot))
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
