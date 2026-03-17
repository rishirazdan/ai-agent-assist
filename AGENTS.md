# AGENTS.md

Guidance for AI coding agents working in this repo.

## Goal

Maintain a stable call-ingestion and QA-analysis pipeline with clear logging and low-friction local testing.

## Repo-Specific Rules

- Keep inbound Twilio voice routing on Studio Flow (`FW<your_voice_ivr_flow_sid>`).
- Use callback endpoint `${PUBLIC_BASE_URL}/twilio/call-completed` for ingestion.
- Preserve PII redaction behavior before persistence.
- Preserve fallback support when OpenAI is unavailable (`OPENAI_DRY_RUN`).

## Key Files

- `app/main.py` webhook + UI endpoints
- `app/twilio_client.py` recordings/auth/download
- `app/openai_client.py` transcription + QA analysis
- `app/redaction.py` text/object redaction
- `scripts/qa_regression.py` regression validation

## Preferred Validation Steps

1. `python scripts/qa_regression.py`
2. `curl http://127.0.0.1:8000/env-check`
3. For live path: verify `data/calls/CA*.json` and `.mp3` created

## Common Failure Modes

- Tunnel URL expired -> webhook misses
- Twilio auth mismatch -> recording list/download fails
- OpenAI quota exhausted -> transcription fails (`429`)

## Documentation Discipline

If architecture, setup, or runbook behavior changes, update:

- `README.md`
- `SETUP.md`
- `ARCHITECTURE.md`
