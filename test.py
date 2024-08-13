import logging
import discord
from discord.ext import commands, voice_recv
import os
import wave
import asyncio
import json
import time
import numpy as np

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
        self.audio_data = {}  # Store audio data for each user separately
        self.channels = 1  # Number of audio channels (Mono)
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
        timestamp = time.strftime("%m-%d-%Y_%I-%M-%S_%p")
        filename = f'{timestamp}_recording.wav'
        
        # Mix audio data
        mixed_audio = self.mix_audio_streams()
        
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.sample_width)
            # Double the frame rate to fix pitch and speed
            wf.setframerate(self.frame_rate * 2)
            wf.writeframes(mixed_audio)
        await ctx.send(f"Saved audio to {filename}")

    def mix_audio_streams(self):
        # Find the length of the longest audio stream
        max_length = max(len(b''.join(data)) for data in self.audio_data.values())
        
        # Initialize an array to hold the mixed audio
        mixed_audio = np.zeros(max_length // self.sample_width, dtype=np.int32)
        
        for user_data in self.audio_data.values():
            user_audio = np.frombuffer(b''.join(user_data), dtype=np.int16)
            mixed_audio[:len(user_audio)] += user_audio
        
        # Normalize the mixed audio to prevent clipping
        mixed_audio = np.clip(mixed_audio, -32768, 32767).astype(np.int16)
        
        return mixed_audio.tobytes()

    @commands.command()
    async def stop(self, ctx):  # Shutdown the bot
        await ctx.send("Shutting down the bot.")
        await self.bot.close()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('------')

async def main():
    async with bot:
        await bot.add_cog(VoiceRecorder(bot))
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())