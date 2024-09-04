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

Add a command to run transcription.py from bot.py.

Maybe use tts to read the summary at the beginning of the next session.

Fix the file naming, not sure why _contenturl_0 is added to the end of the file name.

Automatically delete all the JSON files after the text files are created.

Move the project to a new repository, this one has leaked API keys and I don't want to deal with that. Also make it public so that I can share it with the rest of the group, as well as anyone else who might be interested. Plus I need an MIT license.

Test test.py and test_transcription.py to see if they're functional. If they are they'll replace bot.py and transcription.py.

If I'm merging the audio based on the time, someone who's not there for the beginning of the recording won't get merged in. I'll need to offset the time based on when the person joined the channel and then merge the audio based on that.

## Issues
Merge may be functional.

Summarize is not functional.

Stop recording is only partially functional.