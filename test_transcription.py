# This should be a functional copy of transcription.py, but built for test.py instead of bot.py.

import json
import os
import time
import requests
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import argparse
from datetime import datetime, timedelta

def load_config():
    if not os.path.exists('config.json'):
        raise FileNotFoundError("config.json not found")
    with open('config.json', 'r') as f:
        return json.load(f)
    
config = load_config()

# Load configuration from config.json

# Azure speech configuration
AZURE_SPEECH_KEY = config['AZURE_SPEECH_KEY']
AZURE_SPEECH_REGION = config['AZURE_SPEECH_REGION']

# Azure storage configuration
AZURE_STORAGE_CONNECTION_STRING = config['AZURE_STORAGE_CONNECTION_STRING']
AZURE_STORAGE_CONTAINER_NAME = config['AZURE_STORAGE_CONTAINER_NAME']

# Azure OpenAI configuration (not functional)
# AZURE_OPENAI_ENDPOINT = config['AZURE_OPENAI_ENDPOINT']
# AZURE_OPENAI_DEPLOYMENT = config['AZURE_OPENAI_DEPLOYMENT']
# OPENAI_API_KEY = config['OPENAI_API_KEY']

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

# I'll need to create a stitching function to combine the transcriptions from the different files
def stitch_transcriptions():
    """
    Audio files (and therefore the transcriptions) are split into multiple files with a maximum duration of 10 minutes.
    The format of the names is defined by this:
        timestamp = time.strftime("%m-%d-%Y_%I-%M-%S_%p")
        filename = f'{timestamp}_recording.wav'

    I'll need to stitch the transcriptions together to create a single transcript for the entire audio file.
    I can use the timestamps in the filenames to order the transcriptions correctly
    """
    
    # Check if the transcripts directory exists and if so, list all .txt files
    transcript_files = [f for f in os.listdir("transcripts") if f.endswith('.txt')]
    if not transcript_files:
        print("No transcript files found.")
        return
    
    # Sort the transcript files based on the timestamp in the filename
    transcript_files.sort(key=lambda x: datetime.strptime(x.split("_")[0], "%Y%m%d-%H%M%S"))

    # Get the date that the transcriptions are being stitched
    date = datetime.now().strftime("%m-%d-%Y")

    # Combine the transcriptions into a single transcript in a file named "full_transcript_[date].txt"
    filename = f"full_transcript_{date}.txt"
    with open(f"transcripts/{filename}", "w") as output_file:
        for transcript_file in transcript_files:
            with open(f"transcripts/{transcript_file}", "r") as input_file:
                output_file.write(input_file.read())
                output_file.write("\n\n")
    print(f"Transcriptions stitched together and saved to {filename}")

def main(args):
    if args.transcribe or args.full_run:
        # Check if the recordings directory exists and if so, list all .wav files
        audio_files = [f for f in os.listdir("recordings") if f.endswith('.wav')]
        if not audio_files:
            print("No audio files found.")
            return
        
        # Only keep audio files that don't have corresponding transcripts
        audio_files_to_process = [
            audio_file for audio_file in audio_files
            # I want to get rid of the contenturl stuff but I need to do some testing first.
            if not os.path.exists(f"transcripts/{audio_file.replace('.wav', '_contenturl_0.txt')}")
        ]

        if not audio_files_to_process:
            print("All audio files already have transcriptions.")
        else:
            print("Uploading new audio files to Azure Storage...")
            for audio_file in audio_files_to_process:
                blob_url = upload_to_azure_storage(audio_file)
                
                if blob_url:
                    job_location = submit_batch_transcription_job(blob_url, audio_file)
                    
                    if job_location:
                        files_url = poll_transcription_job(job_location)
                        if files_url:
                            download_transcription_files(files_url, audio_file)


    if args.stitch or args.full_run:
        stitch_transcriptions()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio files using Azure Speech to Text")
    parser.add_argument("--transcribe", action="store_true", help="Transcribe audio files")
    parser.add_argument("--stitch", action="store_true", help="Stitch transcriptions together")
    parser.add_argument("--full-run", action="store_true", help="Run full transcription process")
    
    args = parser.parse_args()
    main(args)
