# BardBot
A discord bot intended to transcribe my DnD sessions on Discord.

## Funtional
### bot.py (potentially deprecated)
Help, join, and leave commands, start and stop recording.

### transcption.py (potentially deprecated)
Transcription of audio files using Azure Speech to Text, all the results are saved to seperate files where they are then stitched together.

TLDR: --transcribe and --stitch fully functional. --summarize is not functional at all.

### test.py (potentially functional)
Most of the changes made to bot.py have not been tested, but the core functionality should still be there. The recording works for at least 2 people in a voice channel, but it still needs to be tested with more people.

### test_transcription.py (potentially functional)
This may also work, I'm not totally sure because I haven't tested it yet. The core functionality is the same as transcription.py, but it's been updated to work with the new test.py (which will replace bot.py).

## Planned
Fix summarize.

Add a command to run transcription.py from bot.py.

Maybe use tts to read the summary at the beginning of the next session.

Fix the file naming, not sure why _contenturl_0 is added to the end of the file name.

Automatically delete all the JSON files after the text files are created.

Move the project to a new repository, this one has leaked API keys and I don't want to deal with that. Also make it public so that I can share it with the rest of the group, as well as anyone else who might be interested. Plus I need an MIT license.

Test test.py and test_transcription.py to see if they're functional. If they are they'll replace bot.py and transcription.py.