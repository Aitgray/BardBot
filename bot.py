import discord
from discord.ext import commands, tasks
import azure.cognitiveservices.speech as speechsdk
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
import os
import wave
import asyncio

# Load environment variables
DISCORD_BOT_TOKEN = "MTI2NjgzMDA0MzMzMDM4Mzg4Mg.GuZ_4k.l7-qXtZWkg_1hNpuf7C1s-HebwG1XF-qTfcfDY"
AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=bardbrain;AccountKey=NXu2E8NN1VyWglGWGoYslmu8WcXWBUPJkc14Ve5pIyEwwhMJLQstZhWniDQ49fzViB疷驸琉Ϡ኷蚍Є==;EndpointSuffix=core.windows.net"
AZURE_STORAGE_CONTAINER_NAME = "bardbrain"
AZURE_SPEECH_KEY = "c224956600314e278141c17783ba6f97"
AZURE_SPEECH_REGION = "uswest"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class VoiceRecorder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recording = False
        self.voice_client = None
        self.audio_frames = []

    @commands.command()
    async def join(self, ctx):
        if ctx.author.voice:
            self.voice_client = await ctx.author.voice.channel.connect()
            await ctx.send("Connected to the voice channel.")
        else:
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
            self.save_audio(ctx)
        else:
            await ctx.send("The bot is not recording.")

    def save_audio(self, ctx):
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
        blob_url = f"https://{AZURE_STORAGE_CONNECTION_STRING.split(';')[2].split('=')[1]}.blob.core.windows.net/{AZURE_STORAGE_CONTAINER_NAME}/{filename}"
        
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        audio_config = speechsdk.AudioConfig(filename=filename)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        result = recognizer.recognize_once()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            self.bot.loop.create_task(self.send_transcription(filename, result.text))
        else:
            print(f"Speech recognition failed: {result.reason}")

    async def send_transcription(self, filename, transcription):
        channel = self.bot.get_channel(int(filename.split('_')[1].split('.')[0]))
        await channel.send(f"Transcription for {filename}: {transcription}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('------')

async def setup_hook():
    await bot.add_cog(VoiceRecorder(bot))

loop = asyncio.get_event_loop()
loop.create_task(setup_hook())
bot.run(DISCORD_BOT_TOKEN)