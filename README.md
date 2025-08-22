# BardBot
A discord bot intended to transcribe my DnD sessions on Discord.

## Funtional
### bot.py
Help, join, and leave commands, start and stop recording.

### transcption.py
Transcription of audio files using Azure Speech to Text, all the results are saved to seperate files where they are then stitched together.

TLDR: --transcribe and --stitch fully functional. --summarize is not functional at all.

### test.py
Recording is partially functional, merging is not functional. There's a bug where the recording can be stopped multiple times ie the recording doesn't actually end.

### test_transcription.py (potentially functional)
This has not been tested.

## Planned
If I'm merging the audio based on the time, someone who's not there for the beginning of the recording won't get merged in. I'll need to offset the time based on when the person joined the channel and then merge the audio based on that. - This seems to have more weight that I initially thought, I'll need to do some testing to see if this is actually a problem. It's possible the silence isn't added at the beginning of the audio file, the file starts the first time someone speaks which is problematic.

Automatically delete all the JSON files after the text files are created.

Move the project to a new repository, this one has leaked API keys and I don't want to deal with that. Also make it public so that I can share it with the rest of the group, as well as anyone else who might be interested. Plus I need an MIT license.

Add a command to run transcription.py from bot.py (this will require the transcription file to be imported which is a bit of a undertaking).

Maybe use tts to read the summary at the beginning of the next session.

Modify bot.py to handle the upload of the audio files, I'll use a seperate thread to handle the upload so that the bot can continue to function while the audio is being uploaded.

Also figure out how to add a progress bar for the transcription, even if it's just how many files are completed vs how many files are left.

## Issues

---

### `local_bot.py` Status

The `local_bot.py` file is a newer, local-focused version of the bot. It uses the `discord-ext-voice-recv` library for voice handling and `local_transcription.py` for transcription. Many of the advanced features are currently implemented as **pseudocode** and will require further development to become functional.

**Implemented Features:**

*   Joining and leaving voice channels.
*   Recording audio from multiple users and saving it to individual `.wav` files (diarization).
*   Local transcription of the `.wav` files using the `speech_recognition` library.

**Features Implemented as Pseudocode:**

*   **SQLite Integration:** The logic for saving transcriptions to a SQLite database is laid out in the `save_audio` function but is not yet functional.
*   **LLM Summarization with RAG:** The `summarize` command contains pseudocode for a Retrieval-Augmented Generation (RAG) system. This system is designed to:
    *   Use notes from an Obsidian vault as context.
    *   Use previously generated summaries as context.
    *   Send the context and the current transcript to a local LLM for summarization.
*   **Discord Summary Posting:** The `post_summary` function has pseudocode for posting the generated summary to a specific Discord channel.
*   **Text-to-Speech (TTS):** The `read_summary` command has pseudocode for using a local TTS engine to read the summary back into the voice channel.
Merge may be functional.

I need to create a copy of the bot that uses open source software instead of Azure.
* The voice_recv library has speech recognition built in now, so I can use that instead of Azure.
* I may want to use something like SQLite to store the transcriptions.
    * This would allow for easier querying and retrieval of past transcriptions.
    * I could use it to train an AI model for better transcription accuracy, as well as for speaker identification. (As well as implementing a more cohesive summarization)
* I'd like to look into implementing TTS as well.

Summarize is not functional:
* I need to get a local LLM running
    * It needs a context window of at least 100k tokens, or I need to break the text into smaller chunks.
    * I believe my hardware can support a model with 30B parameters.
    * I should use RAG so I can tie it into my notes from Obsidian.
    * I'll also need to figure out system prompts and whatnot.