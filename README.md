# AI Agent Assist (PoC) - Amazing Bank

Call-center analytics proof-of-concept that combines Twilio Voice + Studio with OpenAI transcription and QA scoring.



## What It Does

- Receives Twilio call completion webhooks in `app/main.py`
- Downloads recordings via `app/twilio_client.py`
- Transcribes + analyzes calls via `app/openai_client.py`
- Redacts sensitive data via `app/redaction.py`
- Saves results to `data/calls/*.json` and `data/calls/*.mp3`
- Shows call dashboard/detail in `/calls` and `/calls/{call_sid}`

## Quickstart (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:

- `http://127.0.0.1:8000/calls`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/env-check`

## Key Docs

- Setup/runbook: `SETUP.md`
- Architecture + design decisions: `ARCHITECTURE.md`
- Contributor workflow: `CONTRIBUTING.md`
- Agent automation guidance: `AGENTS.md`
- Security operations + key rotation policy: `SECURITY.md`
- Demo evidence checklist: `demo/ACCEPTANCE_ARTIFACTS.md`

## Current IVR Integration

- Number `+1XXXXXXXXXX` routes inbound voice to Studio Flow:
  - `FW<your_voice_ivr_flow_sid>` (`Voice IVR`)
- Recording/completion callback should point to:
  - `${PUBLIC_BASE_URL}/twilio/call-completed`

## Twilio IVR Work Completed

The project is not just consuming Twilio webhooks; it also configured Twilio resources directly:

- Updated Studio Flow `FW<your_voice_ivr_flow_sid>` via Studio API v2
- Implemented 5-option IVR menu:
  - 1 balance inquiry
  - 2 lost/stolen card
  - 3 speak to agent
  - 4 dispute a transaction
  - 5 online/mobile access help
- Added opening recording disclaimer and invalid/no-input loops
- Preserved Flex handoff and passed menu metadata in task attributes
- Added call-recording step in flow before Flex enqueue
- Kept Twilio number `voice_url` on Studio flow and configured number `status_callback` to app webhook endpoint

In short: Twilio IVR creation/configuration and app ingestion were both implemented in this repo workflow.

## MCP Usage and Client Differences

### What MCP was used for

- Initial Twilio account/resource discovery through the `user-t` MCP server
- Fast read checks while bootstrapping the PoC (account SID/resource visibility)
- Studio IVR updates from Codex after enabling Studio service exposure on `t`

### Limitation seen in Cursor settings

- Cursor MCP setup enforced a combined `server:tool` name-length cap (60 chars)
- A subset of long Twilio tool names was skipped/disabled because of that cap

### Codex app behavior

- Codex MCP exposure did not have the same blocking behavior for these tools
- With `--services twilio_api_v2010,twilio_studio_v2`, Codex exposed Studio v2 tools and successfully applied IVR edits via MCP (including publish/verify flow updates)

Net: in this repo, MCP from Codex is sufficient for both discovery and Studio IVR maintenance. Direct Twilio API remains a fallback option.

## Troubleshooting (Fast Path)

- Twilio signature validation is enabled by default (`TWILIO_VALIDATE_SIGNATURE=1`).
  - For local troubleshooting only, temporarily disable with `TWILIO_VALIDATE_SIGNATURE=0`.
- `/env-check` can be protected with `ADMIN_TOKEN` (optional).
- `/calls` and `/calls/{call_sid}` can be protected with `UI_ACCESS_TOKEN` (optional, recommended for public tunnels).
- Set `DELETE_AUDIO_AFTER_TRANSCRIBE=1` if you do not want call audio retained on disk.
- `insufficient_quota` from OpenAI:
  - API billing is separate from ChatGPT Plus
- No live call JSON in `data/calls/`:
  - Check callback reachability + recording availability
- `401` from Twilio recording APIs:
  - Verify `TWILIO_ACCOUNT_SID` and API key/secret pair
- Tunnel instability:
  - Prefer Cloudflare Tunnel over short-lived localtunnel URLs

Webhook retry behavior:

- Handler now returns 5xx on transient processing failures so Twilio can retry delivery.

## CI

- GitHub Actions regression workflow: `.github/workflows/qa-regression.yml`
- Triggered on pull requests to `main`
- Runs `scripts/qa_regression.py` against a local CI-started API server
