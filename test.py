import azure.cognitiveservices.speech as speechsdk
import json
import os
import time
from pydub import AudioSegment
import requests

def load_config():
    if not os.path.exists('config.json'):
        print("Config file not found.")
        return None

    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()

if config is None:
    raise FileNotFoundError("Config file is missing. Please ensure config.json is present.")

AZURE_SPEECH_KEY = config['AZURE_SPEECH_KEY']
AZURE_SPEECH_REGION = config['AZURE_SPEECH_REGION']
AZURE_OPENAI_ENDPOINT = config['AZURE_OPENAI_ENDPOINT']
AZURE_OPENAI_DEPLOYMENT = config['AZURE_OPENAI_DEPLOYMENT']
OPENAI_API_KEY = config['OPENAI_API_KEY']

def transcribe_audio(filename, timestamp):
    print(f"Transcribing audio from {filename}")
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
    audio_config = speechsdk.AudioConfig(filename=filename)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    result = recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        transcription = result.text
        print(f"Transcription recognized: {transcription}")
        save_transcription(filename, transcription, timestamp)
    else:
        print(f"Speech recognition failed: {result.reason}")
        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"CancellationDetails: Reason={cancellation_details.reason}, ErrorDetails={cancellation_details.error_details}")

def save_transcription(filename, transcription, timestamp):
    transcription_filename = filename.replace('.wav', '.txt')
    with open(transcription_filename, 'w') as f:
        f.write(f"Timestamp: {timestamp}\n\n{transcription}")
    print(f"Saved transcription to {transcription_filename}")

def compress_audio(filename):
    print(f"Compressing {filename}")
    audio = AudioSegment.from_wav(filename)
    compressed_filename = filename.replace('.wav', '.mp3')
    audio.export(compressed_filename, format="mp3")
    print(f"Compressed {filename} to {compressed_filename}")
    return compressed_filename

def summarize_transcriptions(transcriptions_text):
    headers = {
        "Content-Type": "application/json",
        "api-key": OPENAI_API_KEY,
    }
    
    data = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Summarize the following transcriptions: {transcriptions_text}"}
        ],
        "temperature": 0.3,
        "max_tokens": 60
    }

    response = requests.post(
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2024-02-15-preview",
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        print("Summary created successfully.")
        summary = response.json()['choices'][0]['message']['content'].strip()
        return summary
    else:
        print(f"Failed to create summary: {response.status_code}")
        print(response.text)
        return None

def main():
    audio_files = [f for f in os.listdir() if f.endswith('.wav')]
    if not audio_files:
        print("No audio files found.")
        return
    
    for audio_file in audio_files:
        if os.path.exists(audio_file.replace('.wav', '.txt')):
            audio_files.remove(audio_file)

    if not audio_files:
        print("All audio files already have transcriptions.")
        return
    else:
        print("Transcribing audio files...")
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        for audio_file in audio_files:
            transcribe_audio(audio_file, timestamp)

    for audio_file in audio_files:
        compressed_filename = compress_audio(audio_file)

    print("Transcription complete.")

    transcriptions = [f for f in os.listdir() if f.endswith('.txt')]
    if not transcriptions:
        print("No transcriptions found.")
        return
    
    transcriptions_text = ""
    for transcription in transcriptions:
        with open(transcription, 'r') as f:
            transcriptions_text += f.read()

    summary = summarize_transcriptions(transcriptions_text)

    if summary:
        print("Summary:", summary)
        with open('summary.txt', 'w') as f:
            f.write(summary)

if __name__ == "__main__":
    main()
