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

# Next steps:
# Actionable Plan: Local Transcript Summarization Bot (RAG + Optional MCP + Ensemble + TTS)

## 0) Goals and Constraints

**Primary goal**

* Produce **high-precision summaries** of multi-speaker (4–6) transcripts (D&D sessions) with consistent structure and minimal hallucination.

**Constraints / preferences**

* Local inference on **RTX 4090 (24GB VRAM)**, ideally via Docker.
* Prefer **100k+ context** when feasible; otherwise use **chunking + map-reduce** to achieve precision.
* Integrate **RAG** with an **Obsidian vault** (notes + lore).
* Optional: MCP-style tool integration (where MCP support is largely a *client/framework property*, not model weights).
* Optional: capture audio from Spotify (high risk: DRM/legal/technical constraints).
* Optional: **TTS** to read last session’s summary at session start.

---

## 1) Phase 1 — Establish a Minimal, Working End-to-End Pipeline

### 1.1 Build a baseline “MVP flow”

**Input**: audio recording → **ASR** (transcription + timestamps) → **speaker segmentation** → **summary**
**Output**: structured summary + persisted data.

Deliverables:

* A script/CLI that takes an audio file and outputs:

  * `transcript.jsonl` (turn-level entries)
  * `summary.md` (final structured summary)

Recommended MVP choices:

* ASR: **Whisper** (local) or faster variants (e.g., faster-whisper).
* Speaker attribution: start with “best effort” (diarization later if needed), or use diarization if you already have a workflow.

Acceptance criteria:

* One full session processed end-to-end with a summary you would actually use.

---

## 2) Phase 2 — Storage Layer (SQLite) for Transcripts + Summaries + Metadata

### 2.1 SQLite schema (minimal but extensible)

Use SQLite as your durable source-of-truth; it keeps querying simple and supports retrieval for RAG.

**Tables**

* `sessions`

  * `session_id` (PK), `started_at`, `ended_at`, `title`, `source` (discord/other), `audio_path`, `notes`
* `speakers`

  * `speaker_id` (PK), `display_name`, `aliases`, `notes`
* `utterances`

  * `utterance_id` (PK), `session_id` (FK), `speaker_id` (FK nullable), `t_start_ms`, `t_end_ms`, `text`, `confidence`, `turn_index`
* `summaries`

  * `summary_id` (PK), `session_id` (FK), `model`, `prompt_profile`, `summary_md`, `created_at`
* `summary_scores`

  * `summary_id` (FK), `judge_model`, `score_json`, `overall_score`, `created_at`

### 2.2 Query patterns you’ll want early

* “Find last session summary”
* “Retrieve all utterances between timestamps”
* “Search utterances by keyword”
* “Get all lore-relevant utterances mentioning X”

Acceptance criteria:

* You can re-run summarization without recomputing ASR.
* You can retrieve and inspect per-turn text reliably.

---

## 3) Phase 3 — Local LLM Serving in Docker (Single-Model First)

### 3.1 Choose the serving stack

Pick one of these patterns and standardize it:

* **vLLM** container (strong for throughput; good for long context depending on model support)
* **Text Generation Inference (TGI)** container (robust, production-oriented)
* **llama.cpp**-based container (simple; often best for quantized models; long context depends on build/config)

**MVP requirement**

* One model accessible via HTTP (OpenAI-compatible API strongly preferred).

### 3.2 Model selection strategy (practical for 24GB)

Given VRAM limits:

* Treat **“100k+ context”** as achievable in two ways:

  1. **True long-context model** (128k) with aggressive quantization and/or partial offload
  2. **Chunking + map-reduce**, which often yields higher precision anyway

**Pragmatic recommendation**

* Start with a **high-quality mid-size model** that fits comfortably (often 7B–30B class quantized) and implement chunking.
* Add a long-context model only after the pipeline is stable.

Acceptance criteria:

* You can send a test prompt and get stable responses at acceptable latency.
* You can run the container reliably across reboots.

---

## 4) Phase 4 — Summarization Pipeline for Precision

### 4.1 Transcript normalization (critical for multi-speaker precision)

Implement a canonical transcript format before the LLM sees it:

* One utterance per line, include timestamp and speaker label when available:

  * `[00:12:03–00:12:17] DM: text…`
* If diarization is imperfect, still keep consistent speaker IDs (S1..S6).

### 4.2 Chunking plan (default)

Even if you have 100k context, chunking is often better for precision.

**Chunking heuristic**

* Split on topic boundaries if possible; otherwise:

  * chunk by time (e.g., 5–10 minutes) OR by token estimate (e.g., 3k–8k tokens)
* Keep overlapping context:

  * 10–20% overlap or “carryover buffer” of the last N turns

### 4.3 Map-reduce summarization

**Map step (per chunk)**

* Produce:

  * bullet summary
  * decisions made
  * open questions
  * NPCs/locations/items mentioned
  * “moments to revisit”

**Reduce step (global)**

* Merge chunk summaries into:

  * Executive recap (short)
  * Detailed timeline (medium)
  * DM notes / hooks (optional)
  * Player-actionable next steps

Acceptance criteria:

* Summary is consistent across sessions, easy to scan, and minimizes invented details.
* You can regenerate summary from stored utterances deterministically (prompt versions tracked).

---

## 5) Phase 5 — RAG Integration with Obsidian

### 5.1 Index sources

* Obsidian vault markdown files (campaign notes, NPC sheets, lore docs)
* Prior session summaries (from SQLite)
* Optional: structured entities extracted from transcripts (NPCs, places)

### 5.2 Retrieval design

* Chunk Obsidian notes into semantic blocks (e.g., headings/sections)
* Build embeddings + vector index (local)
* For summarization, retrieve:

  * “relevant lore” for terms detected in the transcript (NPC names, locations, factions)
  * “prior session summary” and “open threads” automatically

### 5.3 Prompt contract for RAG

Enforce a strict policy:

* The model must label statements as:

  * **From transcript**
  * **From retrieved notes**
  * **Inference**
* If uncertain, it must say “unclear from transcript.”

Acceptance criteria:

* Summaries cite which retrieved notes influenced them.
* You can answer: “Why does the summary say this?” with traceability.

---

## 6) Phase 6 — Multi-Model Ensemble + Trust Scoring

### 6.1 Ensemble roles

Run 2–3 “writer” models and 1 “judge/merger” model.

**Writer models (parallel or sequential)**

* Same chunk inputs, different prompt profiles:

  * Profile A: strict factual, minimal interpretation
  * Profile B: narrative recap (still factual)
  * Profile C: DM-centric hooks and consequences

**Judge/merger model**

* Inputs:

  * transcript chunk (or chunk summary)
  * the candidate summaries
  * retrieved context snippets (optional)
* Output:

  * merged summary
  * per-model trust scores + rationale
  * list of questionable claims + what evidence is missing

### 6.2 Trust metrics (keep simple and operational)

Maintain a config with weights you can tune:

**Automatic signals**

* **Extractiveness score**: how often it quotes/paraphrases directly from transcript
* **Entity consistency**: does it preserve names/roles correctly
* **Contradiction checks**: flagged inconsistencies between writers
* **RAG grounding**: if it uses notes, does it cite them

**Judge output schema (store in SQLite)**

* `overall_score` (0–1)
* `faithfulness_score`
* `coverage_score`
* `clarity_score`
* `hallucination_risk`
* `notes_used` list

Acceptance criteria:

* You can identify which writer model is most reliable over time.
* You can periodically adjust weights without changing code.

---

## 7) Phase 7 — Audio Capture and Recording Orchestration

### 7.1 Discord recording (recommended baseline)

* Bot joins voice channel and records participants.
* Start/stop logic:

  * manual command (most robust)
  * automatic start when all players present (optional)
  * safety timeout + manual override

### 7.2 Spotify audio piping (high-risk / likely non-goal)

This is often blocked by DRM and platform policy. If your objective is “record what we listened to,” consider alternatives:

* Capture **your own microphone + Discord voice** only (legal/clean)
* Or record a “reference track list” (timestamps + Spotify URLs) rather than the audio itself

If you still pursue it technically:

* You’d be in “virtual audio device / mixer” territory.
* Expect fragility and potential ToS issues.
* Treat as an experimental branch, not core.

Acceptance criteria:

* Recording is reliable and produces clean audio artifacts for ASR.

---

## 8) Phase 8 — TTS Readback at Session Start

### 8.1 TTS pipeline

* At session start:

  1. fetch “last session summary” from SQLite
  2. generate a short readback script (optional LLM step)
  3. TTS synthesize
  4. play into Discord voice channel
  5. then start recording automatically

### 8.2 Orchestration details

* Implement an explicit state machine:

  * `IDLE → JOINED → PLAYING_TTS → RECORDING → PROCESSING → IDLE`
* Gate recording start on TTS completion event.
* Yes, the bot can invoke its own command internally, but it’s cleaner to call the function directly.

Acceptance criteria:

* Readback plays cleanly.
* Recording starts immediately after readback, without clipping.

---

## 9) Phase 9 — Always-On, Low-Impact Docker Deployment + Metrics

### 9.1 Architecture

Split into services (compose):

* `bot-service` (Discord connectivity, command handling, scheduling)
* `asr-service` (optional; can be invoked on-demand)
* `llm-service` (vLLM/TGI)
* `rag-service` (embeddings + retrieval index)
* `db` (SQLite volume mount; or SQLite in bot container with a persistent volume)

### 9.2 Resource controls

* LLM service runs idle until called (or keep warm if acceptable)
* Use GPU only in LLM container; bot container CPU-only
* If you do ensemble, run writers sequentially unless you confirm VRAM headroom

### 9.3 Usage metrics (essential for “low impact”)

Track:

* GPU VRAM usage, GPU utilization
* inference latency per request
* tokens generated per session
* ASR runtime
* error rates

Store in SQLite (`metrics` table) and optionally expose Prometheus metrics.

### 9.4 Reminders + automation

If always online:

* Scheduled reminders to DnD channel (e.g., “session in 1 hour”)
* Auto-start recording when quorum is present (optional; provide a manual override)

Acceptance criteria:

* Bot stays connected for days without manual intervention.
* You can review resource consumption after each session.

---

## 10) Implementation Order (Recommended)

1. **MVP pipeline**: audio file → ASR → summary output
2. **SQLite storage** for sessions/utterances/summaries
3. **Single local LLM in Docker** + stable prompts
4. **Chunking + map-reduce summarization** (precision-first)
5. **RAG with Obsidian** (retrieve prior notes + lore)
6. **Ensemble writers + judge** with stored trust metrics
7. **Discord orchestration** (recording + commands)
8. **TTS readback** + state machine gating
9. **Always-on deployment + metrics**
10. **Spotify audio experiment** (only if still needed)

---

## 11) Immediate Next Actions (Concrete Checklist)

### This week

* [ ] Stand up SQLite schema + write insert/query helpers
* [ ] Implement transcript normalization (utterances with timestamps)
* [ ] Run one session through: ASR → SQLite → summary.md

### Next

* [ ] Run a local LLM container and integrate summarization API calls
* [ ] Implement chunking + map-reduce prompts (versioned prompt profiles)
* [ ] Add Obsidian ingestion + vector index + retrieval into prompts

### After that

* [ ] Add 2-writer + 1-judge ensemble, persist trust scores
* [ ] Add Discord recording orchestration (manual start/stop)
* [ ] Add TTS readback + state machine + auto-start recording post-TTS
* [ ] Add metrics collection and resource controls