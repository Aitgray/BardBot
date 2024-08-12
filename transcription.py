import json
import os
import time
import requests
from azure.storage.blob import BlobServiceClient, BlobClient, generate_blob_sas, BlobSasPermissions
import argparse
from datetime import datetime, timedelta

def load_config():
    if not os.path.exists('config.json'):
        print("Config file not found.")
        return None

    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()

if config is None:
    raise FileNotFoundError("Config file is missing. Please ensure config.json is present.")

# Load configuration from config.json
AZURE_SPEECH_KEY = config['AZURE_SPEECH_KEY']
AZURE_SPEECH_REGION = config['AZURE_SPEECH_REGION']
AZURE_OPENAI_ENDPOINT = config['AZURE_OPENAI_ENDPOINT']
AZURE_OPENAI_DEPLOYMENT = config['AZURE_OPENAI_DEPLOYMENT']
OPENAI_API_KEY = config['OPENAI_API_KEY']
AZURE_STORAGE_CONNECTION_STRING = config['AZURE_STORAGE_CONNECTION_STRING']
AZURE_STORAGE_CONTAINER_NAME = config['AZURE_STORAGE_CONTAINER_NAME']

# Check if the file exists in Azure Storage
def blob_exists(filename):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    blob_client = blob_service_client.get_blob_client(container=AZURE_STORAGE_CONTAINER_NAME, blob=filename)
    
    return blob_client.exists()

# Upload the file to Azure Storage
def upload_to_azure_storage(filename):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(filename)
    
    # Check if the blob already exists
    if blob_client.exists():
        print(f"Blob {filename} already exists in Azure Storage. Generating SAS URL.")
    else:
        print(f"Uploading {filename} to Azure Blob Storage")
        with open(f"recordings/{filename}", "rb") as data:
            blob_client.upload_blob(data)
        print(f"Audio uploaded to Azure Storage as {filename}")

    # Generate a SAS URL valid for 24 hours
    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=AZURE_STORAGE_CONTAINER_NAME,
        blob_name=filename,
        account_key=blob_service_client.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=24)
    )
    
    sas_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{AZURE_STORAGE_CONTAINER_NAME}/{filename}?{sas_token}"
    return sas_url

# Submit a batch transcription job to Azure Speech to Text
def submit_batch_transcription_job(blob_url, filename):
    transcription_config = {
        "displayName": filename,
        "description": "Speech Studio Batch speech to text",
        "locale": "en-us",
        "contentUrls": [blob_url],
        "model": {
            "self": "https://westus.api.cognitive.microsoft.com/speechtotext/v3.2/models/base/1125d1a6-1629-4d71-a8ee-d0964ff8f776"
        },
        "properties": {
            "wordLevelTimestampsEnabled": False,
            "displayFormWordLevelTimestampsEnabled": True,
            "diarizationEnabled": False,
            "punctuationMode": "DictatedAndAutomatic",
            "profanityFilterMode": "Masked"
        },
        "customProperties": {}
    }

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(
        f"https://{AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/speechtotext/v3.2/transcriptions",
        headers=headers,
        json=transcription_config
    )

    if response.status_code in [201, 202]:
        print(f"Transcription job for {filename} submitted successfully.")
        return response.headers["Location"]
    else:
        print(f"Failed to submit transcription job for {filename}: {response.status_code}")
        print(response.text)
        return None

# Poll the transcription job status until it is completed
def poll_transcription_job(job_location):
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY
    }

    while True:
        response = requests.get(job_location, headers=headers)
        if response.status_code != 200:
            print(f"Failed to poll transcription job: {response.status_code}")
            print(response.text)
            return None

        job_data = response.json()

        if job_data["status"] == "Succeeded":
            print("Transcription job completed successfully.")
            return job_data["links"]["files"]

        if job_data["status"] == "Failed":
            print("Transcription job failed.")
            print(job_data)
            return None

        print("Transcription job is still in progress. Waiting 30 seconds before polling again...")
        time.sleep(30)

# Download the transcription files from Azure Speech to Text
def download_transcription_files(files_url, original_filename, save_dir="transcripts"):
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY
    }

    response = requests.get(files_url, headers=headers)
    if response.status_code == 200:
        files_data = response.json()
        for file_info in files_data["values"]:
            file_url = file_info["links"]["contentUrl"]
            file_name = file_info["name"]
            file_content = requests.get(file_url).content
            # Rename the files to match the original .wav file
            new_file_name = original_filename.replace('.wav', f'_{file_name}')
            file_path = os.path.join(save_dir, new_file_name)
            
            with open(file_path, "wb") as f:
                f.write(file_content)
            print(f"Downloaded transcription file: {new_file_name}")

            # Process contenturl_0.json to extract transcription
            if 'contenturl_0.json' in new_file_name:
                with open(file_path, "r") as json_file:
                    transcription_data = json.load(json_file)
                    transcription_text = extract_transcription_text(transcription_data)
                    txt_file_name = new_file_name.replace(".json", ".txt")
                    txt_file_path = os.path.join(save_dir, txt_file_name)
                    with open(txt_file_path, "w") as txt_file:
                        txt_file.write(transcription_text)
                    print(f"Extracted transcription text to: {txt_file_path}")
                    # Ensure the file is created and logged
                    if not os.path.exists(txt_file_path):
                        raise FileNotFoundError(f"Failed to create transcription text file: {txt_file_path}")
    else:
        print(f"Failed to download transcription files: {response.status_code}")
        print(response.text)

# Extract the transcription text from the json file downloaded from Azure Speech to Text
def extract_transcription_text(transcription_data):

    transcription_text = ""
    for segment in transcription_data["combinedRecognizedPhrases"]:
        transcription_text += segment["display"] + "\n"
    return transcription_text

# Stitch together the transcriptions for each user (this will be depreciated in the future)
def stitch_transcriptions():
    # List of transcriptions ending with '_contenturl_0.txt'
    transcriptions = [f for f in os.listdir("transcripts") if f.endswith('_contenturl_0.txt')]
    if not transcriptions:
        print("No transcriptions found.")
        return

    user_transcripts = {}

    # Iterate over each transcription file
    for transcription in transcriptions:
        # Extract the user ID from the filename
        # Filename format: 20240808-214120_805576398369849344_contenturl_0.txt
        base_filename_parts = transcription.split('_')
        if len(base_filename_parts) >= 3:
            user_id = base_filename_parts[1]  # Second part is the user ID
        else:
            print(f"Unexpected filename format: {transcription}")
            continue

        transcription_path = os.path.join("transcripts", transcription)
        if not os.path.exists(transcription_path):
            print(f"File not found: {transcription_path}")
            continue

        with open(transcription_path, 'r') as f:
            # Read only the first line to avoid duplicates
            first_line = f.readline().strip()
        
        # Add the first line under the corresponding user ID
        if user_id not in user_transcripts:
            user_transcripts[user_id] = []
        
        user_transcripts[user_id].append(first_line)

    stitched_transcripts = {}
    for user_id, transcripts in user_transcripts.items():
        # Stitch together all the unique first lines
        stitched_transcript = f"User ID: {user_id}\n\n" + "\n\n".join(set(transcripts))
        stitched_transcripts[user_id] = stitched_transcript
        with open(f"transcripts/stitched_{user_id}.txt", 'w') as f:
            f.write(stitched_transcript)
        print(f"Stitched transcription for user {user_id} saved as stitched_{user_id}.txt")

    final_transcript = ""
    for user_id, transcript in stitched_transcripts.items():
        final_transcript += transcript + "\n\n"

    # Write the combined transcript to a single file
    with open('transcripts/final_transcript.txt', 'w') as f:
        f.write(final_transcript)
    print("Final combined transcript saved as final_transcript.txt")

# Summarize the transcriptions using OpenAI's GPT-3 (Not functional)
def summarize_transcriptions(transcriptions_text):
    headers = {
        "Content-Type": "application/json",
        "api-key": OPENAI_API_KEY,
    }
    
    data = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant who summarizes the transcriptions from my DND sessions with friends."},
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
            if os.path.exists(f"transcripts/{audio_file.replace('.wav', '_contenturl_0.txt')}"):
                audio_files.remove(audio_file)

        if not audio_files:
            print("All audio files already have transcriptions.")
        else:
            print("Uploading new audio files to Azure Storage...")
            for audio_file in audio_files:
                blob_url = upload_to_azure_storage(audio_file)
                
                if blob_url:
                    job_location = submit_batch_transcription_job(blob_url, audio_file)
                    
                    if job_location:
                        files_url = poll_transcription_job(job_location)
                        if files_url:
                            download_transcription_files(files_url, audio_file)

    if args.stitch or args.full_run:
        stitch_transcriptions()

    if args.summarize or args.full_run:
        if os.path.exists('transcripts/final_transcript.txt'):
            with open('transcripts/final_transcript.txt', 'r') as f:
                transcriptions_text = f.read()

            summary = summarize_transcriptions(transcriptions_text)

            if summary:
                print("Summary:", summary)
                with open('transcripts/summary.txt', 'w') as f:
                    f.write(summary)
        else:
            print("Final transcript not found. Skipping summarization.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process audio transcriptions and summarization.")
    parser.add_argument("--transcribe", action="store_true", help="Run the transcription process only.")
    parser.add_argument("--stitch", action="store_true", help="Run the transcription stitching process only.")
    parser.add_argument("--summarize", action="store_true", help="Run the summarization process only.")
    parser.add_argument("--full_run", action="store_true", help="Run the full process (transcribe, stitch, summarize).")
    
    args = parser.parse_args()
    main(args)
