# BardBot

BardBot is a Discord bot that records your DnD sessions, transcribes them, and provides a summary of the conversation. It uses a local-first approach, leveraging open-source tools like Whisper for transcription and a local LLM for summarization.

## Current Features

*   **Voice Recording:** Records all participants in a voice channel.
*   **Transcription:** Uses OpenAI's Whisper to transcribe the recorded audio.
*   **Diarization:** Separates the transcription by speaker.
*   **Summarization:** Uses a local Large Language Model (LLM) to summarize the transcription.
*   **Retrieval-Augmented Generation (RAG):** Can use notes from an Obsidian vault to provide context for the summarization.
*   **Persistent Transcripts:** Transcripts are saved in a canonical JSONL format, enabling reprocessing and retrieval.
*   **Vector Database:** Uses Qdrant to store and retrieve embeddings of transcripts and Obsidian notes.
*   **Local LLM Support:** Integrated with Ollama to run a local LLM for summarization.

## Setup and Usage

The recommended way to run BardBot is with Docker.

1.  **Install Docker and Docker Compose.**
2.  **Create a `config.json` file:**
    *   Copy the `example_config.json` file to `config.json`.
    *   Fill in the required values:
        *   `DISCORD_BOT_TOKEN`: Your Discord bot token.
        *   `OBSIDIAN_VAULT_PATH` (optional): The absolute path to your Obsidian vault.
        *   `WHISPER_MODEL` (optional): The Whisper model to use for transcription. Defaults to `small.en`.
3.  **Run the bot:**
    ```bash
    docker-compose up -d
    ```

## Commands

-   `!join`: Joins the voice channel you are currently in.
-   `!leave`: Leaves the voice channel.
-   `!start_recording`: Starts recording the voice channel.
-   `!stop_recording`: Stops recording and saves the transcript.
-   `!summarize`: Summarizes the current transcript.
-   `!stop`: Shuts down the bot.

## Configuration

The `config.json` file is used to configure the bot.

-   `DISCORD_BOT_TOKEN`: Your Discord bot token. This is required.
-   `OBSIDIAN_VAULT_PATH`: The absolute path to your Obsidian vault. This is optional. If you provide a path, the bot will use your notes as context for the summarization.
-   `WHISPER_MODEL`: The Whisper model to use for transcription. This is optional. Defaults to `small.en`. You can find a list of available models on the [OpenAI Whisper GitHub page](https://github.com/openai/whisper).

# Action Plan — Local RAG-First Transcript Summarization Bot

> Assumptions:
> - Recording, transcription, and diarization are already functional.
> - Goal is **high-precision multi-speaker summaries**.
> - Local inference on RTX 4090 (24 GB VRAM).
> - RAG is required (Obsidian + past sessions).
> - Chunking is preferred over relying on extreme context windows.

---

## 1. Precision-First Summarization Pipeline

- [x] Replace `summarize` placeholder with:
- retrieval → map → reduce → persistence
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

## 1. Multi-Model Ensemble (Optional but Recommended)

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

## 3. RAG Tooling / MCP-Style Integration

- [ ] Expose retrieval as explicit tools:
- `retrieve_transcript_chunks(query)`
- `retrieve_obsidian_notes(query)`
- `get_last_session_summary()`
- [ ] Use tool calls instead of prompt stuffing when possible.

**Why:** MCP is a client/tooling concern; this achieves the same outcome.

---

## 4. TTS Readback (Generate Post-Summarization, Play Pre-Session)

### 4.1 Generate TTS as a post-processing artifact (end of pipeline)
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

### 4.2 Playback behavior at session start (non-blocking, fail-soft)
- [ ] On session start command (or when quorum arrives):
- If `readback.*` exists for the latest completed session: **play immediately**
- If missing: fall back to **text post in chat** (or play nothing), but **do not block recording**
- [ ] Ensure playback never delays recording:
- Recording start should be independent of TTS readiness
- Optionally: start recording first, then play TTS (if you don’t mind it being recorded)

### 4.3 Recording gate logic (choose one)
- [ ] Option A (preferred for clean audio): `PLAY_TTS → START_RECORDING` only if file exists; otherwise start recording immediately.
- [ ] Option B (always-start): `START_RECORDING → PLAY_TTS` (TTS may be included in the recording, but session never waits).

### 4.4 Operational safeguard
- [ ] Add a timeout for TTS playback (e.g., stop after X minutes).
- [ ] Add a manual override command:
- `!readback` (play audio if present)
- `!skipreadback` (stop playback)
- `!record` (force recording start)

---

## 5. Always-On Deployment + Metrics

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