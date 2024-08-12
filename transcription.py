import json
import os
import time
import requests
from azure.storage.blob import BlobServiceClient
import argparse

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
AZURE_STORAGE_CONNECTION_STRING = config['AZURE_STORAGE_CONNECTION_STRING']
AZURE_STORAGE_CONTAINER_NAME = config['AZURE_STORAGE_CONTAINER_NAME']

def submit_batch_transcription_job(blob_url, job_name):
    url = f"https://{AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/speechtotext/v3.2/transcriptions"

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "application/json"
    }

    body = {
        "displayName": job_name,
        "description": "Batch transcription for audio files",
        "locale": "en-US",
        "contentUrls": [blob_url],
        "properties": {
            "wordLevelTimestampsEnabled": False,
            "diarizationEnabled": False,
            "punctuationMode": "DictatedAndAutomatic"
        }
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code == 202:
        print(f"Batch transcription job '{job_name}' submitted successfully.")
        job_location = response.headers['location']
        return job_location
    else:
        print(f"Failed to submit batch transcription job: {response.status_code}")
        print(response.json())
        return None

def poll_transcription_job(job_location):
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY
    }

    while True:
        response = requests.get(job_location, headers=headers)

        if response.status_code == 200:
            job_status = response.json()['status']
            if job_status in ['Succeeded', 'Failed']:
                print(f"Job finished with status: {job_status}")
                return response.json()
            else:
                print(f"Job status: {job_status}. Polling again in 30 seconds...")
                time.sleep(30)
        else:
            print(f"Failed to poll job status: {response.status_code}")
            print(response.json())
            return None

def upload_to_azure_storage(filename):
    print(f"Uploading {filename} to Azure Blob Storage")
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(filename)

    with open(f"recordings/{filename}", "rb") as data:
        blob_client.upload_blob(data)

    print(f"Audio uploaded to Azure Storage as {filename}")
    return blob_client.url

def stitch_transcriptions():
    transcriptions = [f for f in os.listdir("transcripts") if f.endswith('.txt')]
    if not transcriptions:
        print("No transcriptions found.")
        return

    user_transcripts = {}

    # Group transcriptions by user ID
    for transcription in transcriptions:
        user_id = transcription.split('_')[-1].split('.')[0]
        with open(transcription, 'r') as f:
            transcript_content = f.read()
        if user_id not in user_transcripts:
            user_transcripts[user_id] = []
        user_transcripts[user_id].append(transcript_content)

    # Stitch together all transcripts for each user
    stitched_transcripts = {}
    for user_id, transcripts in user_transcripts.items():
        stitched_transcript = f"User ID: {user_id}\n\n" + "\n\n".join(transcripts)
        stitched_transcripts[user_id] = stitched_transcript
        with open(f"transcripts/stitched_{user_id}.txt", 'w') as f:
            f.write(stitched_transcript)
        print(f"Stitched transcription for user {user_id} saved as stitched_{user_id}.txt")

    # Combine all user transcripts into one large transcript
    final_transcript = ""
    for user_id, transcript in stitched_transcripts.items():
        final_transcript += transcript + "\n\n"

    with open('transcripts/final_transcript.txt', 'w') as f:
        f.write(final_transcript)
    print("Final combined transcript saved as final_transcript.txt")

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

def main(args):
    if args.transcribe or args.full_run:
        audio_files = [f for f in os.listdir("recordings") if f.endswith('.wav')]
        if not audio_files:
            print("No audio files found.")
            return
        
        for audio_file in audio_files:
            if os.path.exists(f"transcripts/{audio_file.replace('.wav', '.txt')}"):
                audio_files.remove(audio_file)

        if not audio_files:
            print("All audio files already have transcriptions.")
        else:
            print("Uploading audio files to Azure Storage...")
            for audio_file in audio_files:
                blob_url = upload_to_azure_storage(audio_file)
                
                if blob_url:
                    job_location = submit_batch_transcription_job(blob_url, audio_file)
                    
                    if job_location:
                        transcription_result = poll_transcription_job(job_location)
                        # Process the transcription_result as needed

    if args.stitch or args.full_run:
        stitch_transcriptions()

    if args.summarize or args.full_run:
        with open('transcripts/final_transcript.txt', 'r') as f:
            transcriptions_text = f.read()

        summary = summarize_transcriptions(transcriptions_text)

        if summary:
            print("Summary:", summary)
            with open('transcripts/summary.txt', 'w') as f:
                f.write(summary)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process audio transcriptions and summarization.")
    parser.add_argument("--transcribe", action="store_true", help="Run the transcription process only.")
    parser.add_argument("--stitch", action="store_true", help="Run the transcription stitching process only.")
    parser.add_argument("--summarize", action="store_true", help="Run the summarization process only.")
    parser.add_argument("--full_run", action="store_true", help="Run the full process (transcribe, stitch, summarize).")
    
    args = parser.parse_args()
    main(args)
