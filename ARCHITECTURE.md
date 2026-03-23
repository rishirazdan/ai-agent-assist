# Architecture

## System Overview

This PoC separates call control from analytics:

- Call control/IVR in Twilio Studio (`Voice IVR`)
- Processing in local FastAPI service (`app/main.py`)
- AI in OpenAI client (`app/openai_client.py`)
- Persistence in filesystem (`app/storage.py`, `data/calls/`)

## Architecture Diagram

```mermaid
flowchart LR
  A[Caller] --> B[Twilio Number]
  B --> C[Studio Flow FW<your_voice_ivr_flow_sid>]
  C --> D[Status Callback POST /twilio/call-completed]
  D --> E[FastAPI app/main.py]
  E --> F[Twilio API app/twilio_client.py]
  F --> G[Recording MP3]
  E --> H[OpenAI app/openai_client.py]
  H --> I[Transcript + QA JSON]
  E --> J[Storage app/storage.py]
  J --> K[data/calls/*.json + *.mp3]
  K --> L[/calls dashboard]
```

## Key Design Decisions

- **Studio-first IVR**: keep routing and caller interaction in Twilio Studio for low-code maintainability.
- **App-side analytics**: centralize transcript, QA scoring, and redaction in Python for flexibility.
- **File-based persistence**: faster setup than a DB for PoC/demo workflows.
- **Degraded fallback mode**: `OPENAI_DRY_RUN=1` keeps pipeline operational without API calls.
- **PII redaction before storage**: `app/redaction.py` sanitizes transcript/analysis payloads.
- **Retry on recording media fetch**: `app/twilio_client.py` retries when Twilio media is not immediately available.

## MCP Usage and Client-Specific Limits

- **Used for**: Twilio discovery and operational changes via MCP (`t` / `user-t`).
- **Cursor limitation observed**: Cursor MCP settings enforced a combined `server:tool` name-length cap (60 chars). Some Twilio tools (for example long `TwilioApiV2010--...` names) were skipped.
- **Codex app behavior**: Codex did not block those tools in the same way; after enabling `twilio_studio_v2` on MCP server `t`, Studio tools were exposed and used to modify/publish IVR flow changes directly through MCP.
- **Resulting approach**: MCP is a viable control plane here (including Studio flow edits) when run from Codex; direct Twilio API remains a reliable fallback path.

## Important Paths

- API/webhook/UI: `app/main.py`
- Twilio API integration: `app/twilio_client.py`
- OpenAI integration: `app/openai_client.py`
- Redaction logic: `app/redaction.py`
- Storage helpers: `app/storage.py`
- Regression checks: `scripts/qa_regression.py`

## Operational Notes

- Inbound voice webhook should remain on Studio Flow.
- Completion callback should target `${PUBLIC_BASE_URL}/twilio/call-completed`.
- `TWILIO_VALIDATE_SIGNATURE` defaults to enabled. Use `TWILIO_VALIDATE_SIGNATURE=0` only for local troubleshooting.
- On transient ingestion failures, webhook returns 5xx so Twilio retry behavior can recover processing.
