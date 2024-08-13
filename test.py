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
        self.silence_frame = b'\x00' * self.sample_width * self.channels * (self.frame_rate // 100)  # 10ms of silence

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

    def callback(self, user, packet):
        if packet is not None and packet.decrypted_data is not None:
            if user.id not in self.audio_data:
                self.audio_data[user.id] = bytearray()

            # Append audio data or silence
            self.audio_data[user.id].extend(packet.decrypted_data)

            # Ensure all buffers are synchronized in length
            max_length = max(len(data) for data in self.audio_data.values())
            for uid in self.audio_data:
                if len(self.audio_data[uid]) < max_length:
                    self.audio_data[uid].extend(self.silence_frame * ((max_length - len(self.audio_data[uid])) // len(self.silence_frame)))

    async def save_audio(self, ctx):
        timestamp = time.strftime("%m-%d-%Y_%I-%M-%S_%p")
        for user_id, audio in self.audio_data.items():
            user = self.bot.get_user(user_id)
            if user:
                filename = f'recordings/{user.name}_{user_id}_{timestamp}.wav'
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(self.sample_width)
                    wf.setframerate(self.frame_rate)
                    wf.writeframes(b''.join(audio))
                await ctx.send(f"Saved audio for {user.name} to {filename}")

        # Save merged audio for transcription
        merged_filename = f'recordings/merged_{timestamp}.txt'
        merged_audio = self.merge_audio_streams()
        with wave.open(merged_filename, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.sample_width)
            wf.setframerate(self.frame_rate)
            wf.writeframes(merged_audio)
        await ctx.send(f"Saved merged audio to {merged_filename}")

    def merge_audio_streams(self):
        # Find the length of the longest audio stream
        max_length = max(len(data) for data in self.audio_data.values())
        
        # Initialize an array to hold the mixed audio
        mixed_audio = np.zeros(max_length // self.sample_width, dtype=np.int32)
        
        for user_data in self.audio_data.values():
            user_audio = np.frombuffer(user_data, dtype=np.int16)
            mixed_audio[:len(user_audio)] += user_audio
        
        # Clip the values to fit in int16
        mixed_audio = np.clip(mixed_audio, -32768, 32767)
        
        return mixed_audio.astype(np.int16).tobytes()

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