# Setup Guide

## Prerequisites

- Python 3.10+
- Twilio account + number
- OpenAI API key (API billing enabled)

## 1) Install and run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/env-check`

## 2) Required environment variables

Set in PowerShell or `.env`:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe
TWILIO_ACCOUNT_SID=AC...
TWILIO_API_KEY_SID=SK...
TWILIO_API_KEY_SECRET=...
PUBLIC_BASE_URL=https://<public-url>
```

Optional:

- `OPENAI_DRY_RUN=1` (fallback mode, no OpenAI usage)
- `TWILIO_AUTH_TOKEN=...` (fallback Twilio auth mode)
- `TWILIO_VALIDATE_SIGNATURE=1` (default). Set `TWILIO_VALIDATE_SIGNATURE=0` only for local troubleshooting (never in production).
- `ADMIN_TOKEN=...` (optional; when set, `/env-check` requires `X-Admin-Token` or `Authorization: Bearer <token>`)
- `UI_ACCESS_TOKEN=...` (optional; when set, `/calls` and `/calls/{call_sid}` require `?token=<value>` or `ui_token` cookie)
- `DELETE_AUDIO_AFTER_TRANSCRIBE=1` (optional; deletes downloaded call audio after transcription)

## 3) Public callback URL

Use Cloudflare quick tunnel:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8000 --no-autoupdate
```

Take generated URL (for example, `https://<name>.trycloudflare.com`) and set:

```powershell
$env:PUBLIC_BASE_URL="https://<name>.trycloudflare.com"
```

Restart app after updating env vars.

## 4) Twilio configuration

- Inbound voice webhook: keep on Studio Flow `FW<your_voice_ivr_flow_sid>`
- Completion callback: `${PUBLIC_BASE_URL}/twilio/call-completed`
- Method: `POST`

MCP note:

- MCP can help with early Twilio discovery/read checks.
- For this repo, direct Twilio Studio API v2 calls are the primary/most reliable path for flow edits, publish/verify cycles, and callback wiring.

## 5) Smoke tests

Offline:

```powershell
python -m app.offline_demo
python scripts/qa_regression.py
```

Live:

1. Place a test call to IVR number
2. Confirm files in `data/calls/`:
   - `CA....mp3` or `CA....wav` (if deletion disabled)
   - `CA....json`
3. Open `http://127.0.0.1:8000/calls`

## Troubleshooting

- **No webhook hit**: tunnel URL expired or callback URL stale
- **No recording found**: recording not enabled for call leg/flow
- **OpenAI 429 insufficient_quota**: API billing limit or zero budget
- **Twilio 401**: invalid SID/key/secret combination
- **App runs but empty dashboard**: check `data/calls/` write permissions and webhook logs
