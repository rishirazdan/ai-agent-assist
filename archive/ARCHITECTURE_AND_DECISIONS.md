# AI Agent Assist (PoC) - Architecture and Design Decisions (Archived)

This is an archived version of the earlier architecture/design narrative.  
For current architecture and setup guidance, use:

- `ARCHITECTURE.md`
- `SETUP.md`
- `README.md`

## 1) Objective

Build a lightweight, demo-ready call-center analytics PoC for "Amazing Bank" that:

- Receives Twilio call-completion webhooks
- Downloads call recordings
- Produces transcription + QA analysis
- Stores and renders call summaries in a local web UI

## 2) High-Level Architecture

Core components:

- Twilio Voice + Studio Flow (`Voice IVR`)
- FastAPI service (`app/main.py`)
- Twilio API client (`app/twilio_client.py`)
- OpenAI client (`app/openai_client.py`)
- Storage layer (`app/storage.py`)
- Web UI endpoints (`/calls`, `/calls/{call_sid}`)

Flow:

1. Caller reaches Twilio number and is handled by Studio Flow
2. Twilio sends webhook to `/twilio/call-completed`
3. Service validates payload/signature policy and resolves recording URL
4. Recording is downloaded to `data/calls/{CallSid}.mp3`
5. Audio is transcribed and transcript is analyzed for QA
6. Full result is saved to `data/calls/{CallSid}.json`
7. Call appears in `/calls` dashboard and detail page

## 3) Twilio Studio IVR Design (Current at Time of Write)

Target flow updated: `FW<your_voice_ivr_flow_sid>` (`Voice IVR`)

Implemented IVR structure:

- Opening prompt with recording disclaimer
- 5-option menu:
  - 1: Balance inquiry
  - 2: Lost/stolen card
  - 3: Speak to an agent
  - 4: Dispute a transaction
  - 5: Online/mobile banking access help
- Invalid/no-input handling loops back to menu
- Handoff to Flex preserved via `send-to-flex`
- Selected menu metadata carried to Flex task attributes

## 4) Backend Design Choices

- FastAPI entrypoint with minimal endpoints
- Twilio auth strategy: API Key preferred, Auth Token fallback
- Optional signature validation (`TWILIO_VALIDATE_SIGNATURE`)
- File-based storage under `data/calls/`

## 5) OpenAI Design Choices

- Live mode + dry-run fallback mode
- Standardized analysis schema:
  - summaries, sentiment, scores, strengths, improvements, coaching note
- JSON extraction safeguards and graceful fallback

## 6) Logging and Observability

- `Log.section()`, `Log.info/warn/error()`, `Log.kv()`
- Stage-based terminal logs for debugging and demo reliability

## 7) Testing and Validation (At Time of Write)

- Offline validation via `python -m app.offline_demo`
- Regression checks via `scripts/qa_regression.py`
- Runtime checks via `/env-check` and tunnel health checks

## 8) Key Decisions and Rationale

1. Studio-driven IVR, app-driven analytics
2. File storage over database for PoC speed
3. Fallback-first resiliency for demos
4. Incremental hardening approach
5. Explicit regression script for repeatability

## 9) Risks / Open Items (Historical)

- Twilio credential reliability
- Tunnel volatility
- Signature validation not always enabled
- Secret rotation required after testing

## 10) Recommended Next Steps (Historical Snapshot)

1. Stabilize Twilio auth
2. Enforce `TWILIO_VALIDATE_SIGNATURE=1`
3. Use stable ingress endpoint
4. Add masked logging policy
5. Capture full live acceptance evidence
