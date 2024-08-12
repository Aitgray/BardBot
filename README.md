# BardBot
A discord bot intended to transcribe my DnD sessions on Discord.

## Funtional
### bot.py
Help, join, and leave commands, start and stop recording.

### transcption.py
Transcription of audio files using Azure Speech to Text, all the results are saved to seperate files where they are then stitched together.

TLDR: --transcribe and --stitch fully functional. --summarize is not functional.

## Planned
Fix summarize, add a command to run transcription.py from bot.py.

Maybe use tts to read the summary at the beginning of the next session.

Fix the file naming, not sure why _contenturl_0 is added to the end of the file name.

Automatically delete all the JSON files after the text files are created.

Replace the playerID with the player's name or nickname from discord.

Convert the time in the file name to a (slightly) more readable format (maybe instead of hhmmss I can make it hh:dd:ss(AM/PM)).

I need to double check the --transcribe command to ensure that audio files that have been transcribed are not transcribed again. This should just be as simple as checking if the file name is in the list of files that have already been transcribed.

