import logging
import discord
from discord.ext import commands
import azure.cognitiveservices.speech as speechsdk
from azure.storage.blob import BlobServiceClient
import os
import wave
import asyncio
import json

# Load configuration from config.json
def load_config():
    with open('config.json') as config_file:
        config = json.load(config_file)
    return config

config = load_config()

DISCORD_BOT_TOKEN = config["DISCORD_BOT_TOKEN"]
AZURE_STORAGE_CONNECTION_STRING = config["AZURE_STORAGE_CONNECTION_STRING"]
AZURE_STORAGE_CONTAINER_NAME = config["AZURE_STORAGE_CONTAINER_NAME"]
AZURE_SPEECH_KEY = config["AZURE_SPEECH_KEY"]
AZURE_SPEECH_REGION = config["AZURE_SPEECH_REGION"]

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Enable voice state intents

bot = commands.Bot(command_prefix="!", intents=intents)

class VoiceRecorder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recording = False
        self.voice_client = None
        self.audio_frames = []

    @commands.command()
    async def join(self, ctx):
        print("Join command invoked")
        await ctx.send("Join command invoked")
        if ctx.author.voice:
            print(f"Author is in a voice channel: {ctx.author.voice.channel.name}")
            await ctx.send(f"Author is in a voice channel: {ctx.author.voice.channel.name}")
            try:
                self.voice_client = await ctx.author.voice.channel.connect()
                await ctx.send("Connected to the voice channel.")
            except Exception as e:
                print(f"Failed to connect to the voice channel: {e}")
                await ctx.send(f"Failed to connect to the voice channel: {e}")
        else:
            print("Author is not in a voice channel")
            await ctx.send("You are not in a voice channel.")

    @commands.command()
    async def leave(self, ctx):
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
            await ctx.send("Disconnected from the voice channel.")
        else:
            await ctx.send("Not connected to any voice channel.")

    @commands.command()
    async def start_recording(self, ctx):
        if self.voice_client and not self.recording:
            self.recording = True
            self.audio_frames = []
            await ctx.send("Started recording.")
        else:
            await ctx.send("Bot is not connected to a voice channel or already recording.")

    @commands.command()
    async def stop_recording(self, ctx):
        if self.recording:
            self.recording = False
            await ctx.send("Stopped recording.")
            await self.save_audio(ctx)
        else:
            await ctx.send("The bot is not recording.")

    async def save_audio(self, ctx):
        filename = f"recording_{ctx.guild.id}.wav"
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b''.join(self.audio_frames))
        
        self.upload_to_azure_blob(filename)
        os.remove(filename)

    def upload_to_azure_blob(self, filename):
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(filename)

        with open(filename, "rb") as data:
            blob_client.upload_blob(data)

        # Trigger transcription after upload
        self.transcribe_audio(filename)

    def transcribe_audio(self, filename):
        print(f"Transcribing {filename}")
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        audio_config = speechsdk.AudioConfig(filename=filename)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            self.bot.loop.create_task(self.send_transcription(filename, result.text))
        else:
            print(f"Speech recognition failed: {result.reason}")
            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                print(f"CancellationDetails: Reason={cancellation_details.reason}, ErrorDetails={cancellation_details.error_details}")

    async def send_transcription(self, filename, transcription):
        channel_id = int(filename.split('_')[1].split('.')[0])
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(f"Transcription for {filename}: {transcription}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('------')

async def main():
    async with bot:
        await bot.add_cog(VoiceRecorder(bot))
        await bot.start(DISCORD_BOT_TOKEN)

# Main entry point for running locally
if __name__ == "__main__":
    asyncio.run(main())
