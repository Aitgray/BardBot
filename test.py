import logging
import discord
from discord.ext import commands, voice_recv
import os
import wave
import asyncio
import json
import time

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
        self.frame_duration = 1024 / 48000  # Duration of each frame in seconds
        self.silence_frame = b'\x00' * 1024 * self.channels * self.sample_width
        self.last_packet_time = {}  # Track last packet time for each user

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
        self.last_packet_time = {}
        await ctx.send("Started recording")

    @commands.command()
    async def stop_recording(self, ctx):
        print("Stop recording command invoked")
        await ctx.send("Stop recording command invoked")
        self.recording = False
        await self.save_audio(ctx)
        await ctx.send("Stopped recording")

    def callback(self, user, data: voice_recv.VoiceData):
        if self.recording:
            current_time = time.time()
            
            # Initialize user audio data and last packet time if not already present
            if user.id not in self.audio_data:
                self.audio_data[user.id] = []
                self.last_packet_time[user.id] = current_time

            # Calculate time elapsed since last packet
            time_elapsed = current_time - self.last_packet_time[user.id]
            self.last_packet_time[user.id] = current_time

            # Calculate the number of silence frames to insert
            num_silence_frames = int(time_elapsed / self.frame_duration) - 1

            # Insert silence frames if there's a gap
            if num_silence_frames > 0:
                self.audio_data[user.id].extend([self.silence_frame] * num_silence_frames)

            # Append the received audio data
            self.audio_data[user.id].append(data.pcm)

    async def save_audio(self, ctx):
        timestamp = time.strftime("%Y%m%d-%H%M%S")

        for user_id, audio_chunks in self.audio_data.items():
            filename = f'{timestamp}_{user_id}.wav'
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.sample_width)
                wf.setframerate(self.frame_rate)
                wf.writeframes(b''.join(audio_chunks))
            await ctx.send(f"Saved audio to {filename}")

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
