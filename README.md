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

# Action Plan — Local RAG-First Transcript Summarization Bot

> Assumptions:
> - Recording, transcription, and diarization are already functional.
> - Goal is **high-precision multi-speaker summaries**.
> - Local inference on RTX 4090 (24 GB VRAM).
> - RAG is required (Obsidian + past sessions).
> - Chunking is preferred over relying on extreme context windows.

---

## 1. Normalize and Persist Transcripts (Foundational)

- [ ] Introduce a stable `session_id` (e.g., `YYYYMMDD_dnd_<channel>`).
- [ ] Convert existing transcript output into a **canonical format**:
  - One JSONL file per segment (`turns.jsonl`).
  - Fields: `session_id`, `segment_id`, `speaker_label`, `t_start`, `t_end`, `text`.
- [ ] Store sessions on disk as:
  sessions/<session_id>/
  segments/
  summaries/
  metadata.json
**Why:** Enables deterministic summarization, reprocessing, and retrieval.

---

## 2. Stand Up a Vector Database (RAG Core)

- [ ] Choose and deploy a local vector DB (I think I'll go with Qdrant).
- [ ] Define two embedding corpora:
- **Transcripts:** chunked segments or sub-chunks.
- **Obsidian notes:** chunked by heading/section.
- [ ] Store metadata with each embedding:
- `type = transcript | obsidian | summary`
- `session_id`, `speaker_labels`, `tags`, `source_path`.

**Why:** SQLite is insufficient for semantic retrieval; vector DB is required for RAG.

---

## 3. Local LLM Serving in Docker

- [ ] Deploy a single local LLM behind an HTTP API (vLLM / TGI / llama.cpp). (I'll probably use llama.cpp if I'm planning on using a llama based model, I'll probably go with Llama 3.1 8B).
- [ ] Ensure quantization fits comfortably in 24 GB VRAM.
- [ ] Validate:
- Stable responses
- Acceptable latency for batch summarization
- [ ] Treat long context as optional; default to chunked input.

**Why:** Summarization quality > raw context size.

---

## 4. Precision-First Summarization Pipeline

### Map Step (per chunk)
- [ ] Input to LLM:
- Transcript chunk
- Top-k retrieved Obsidian notes
- Top-k retrieved prior summaries
- [ ] Output structure:
- Factual recap (bullets)
- Decisions made
- Open threads
- NPCs / locations / items (grounded)
- Uncertainties explicitly marked

### Reduce Step (per session)
- [ ] Merge chunk summaries into:
- Executive recap
- Timeline
- Party state
- Next-session hooks

**Why:** Chunking + RAG consistently outperforms monolithic summarization.

---

## 5. Multi-Model Ensemble (Optional but Recommended)

- [ ] Run 2–3 **writer passes** with different prompt profiles:
- Factual
- Narrative
- DM-focused
- [ ] Run 1 **judge/admin pass**:
- Compare summaries against transcript + retrieved context.
- Output merged summary + trust scores.

### Trust Metrics (store per summary)
- `faithfulness`
- `coverage`
- `clarity`
- `hallucination_risk`

**Why:** Increases reliability and lets you weight models over time.

---

## 6. RAG Tooling / MCP-Style Integration

- [ ] Expose retrieval as explicit tools:
- `retrieve_transcript_chunks(query)`
- `retrieve_obsidian_notes(query)`
- `get_last_session_summary()`
- [ ] Use tool calls instead of prompt stuffing when possible.

**Why:** MCP is a client/tooling concern; this achieves the same outcome.

---

## 7. TTS Readback (Generate Post-Summarization, Play Pre-Session)

### 7.1 Generate TTS as a post-processing artifact (end of pipeline)
- [ ] After the final session summary is produced, generate a **readback script** (either:
  - the first N bullets of the executive recap, or
  - a dedicated “readback” section produced by the LLM).
- [ ] Synthesize TTS audio immediately (same job) and persist:

sessions/<session_id>/summaries/
summary.md
readback.txt
readback.wav (or .mp3)
readback.meta.json

- [ ] Store metadata:
- `tts_engine`, `voice`, `sample_rate`, `duration_ms`, `created_at`
- `summary_id` or checksum of `summary.md` (so you know the audio matches the summary)

**Goal:** TTS is “ready-to-play” before the next session begins.

### 7.2 Playback behavior at session start (non-blocking, fail-soft)
- [ ] On session start command (or when quorum arrives):
- If `readback.*` exists for the latest completed session: **play immediately**
- If missing: fall back to **text post in chat** (or play nothing), but **do not block recording**
- [ ] Ensure playback never delays recording:
- Recording start should be independent of TTS readiness
- Optionally: start recording first, then play TTS (if you don’t mind it being recorded)

### 7.3 Recording gate logic (choose one)
- [ ] Option A (preferred for clean audio): `PLAY_TTS → START_RECORDING` only if file exists; otherwise start recording immediately.
- [ ] Option B (always-start): `START_RECORDING → PLAY_TTS` (TTS may be included in the recording, but session never waits).

### 7.4 Operational safeguard
- [ ] Add a timeout for TTS playback (e.g., stop after X minutes).
- [ ] Add a manual override command:
- `!readback` (play audio if present)
- `!skipreadback` (stop playback)
- `!record` (force recording start)

---

## 8. Always-On Deployment + Metrics

- [ ] Split services:
- Discord bot (CPU)
- Vector DB (CPU + disk)
- LLM server (GPU)
- [ ] Track basic metrics:
- Summarization runtime
- Tokens generated
- Retrieval hit counts
- GPU utilization
- [ ] Persist metrics as JSONL or lightweight DB.

**Why:** Keeps the bot low-impact and observable.

---

## Immediate Next Actions (High Impact)

- [x] Add `session_id` + canonical transcript format.
- [x] Deploy vector DB and index:
- transcripts
- Obsidian vault
- [ ] Replace `summarize` placeholder with:
- retrieval → map → reduce → persistence
- [ ] Verify one full session produces a usable summary.
- [ ] Implement summarization pipeline using vector DB.

---