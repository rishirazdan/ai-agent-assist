# Security Operations

## Secrets Rotation Policy
- Rotate OpenAI and Twilio secrets at least every 90 days.
- Rotate immediately after any suspected exposure (chat logs, screenshots, terminal paste, or commit history).
- Revoke old keys as soon as replacement keys are verified in runtime.

## Runtime Secret Checklist
- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_API_KEY_SID`
- `TWILIO_API_KEY_SECRET`
- `TWILIO_AUTH_TOKEN`
- `ADMIN_TOKEN`

## Post-Rotation Verification
1. Restart API service.
2. Check `/health` returns `200`.
3. Check `/env-check` returns `401` without admin token and `200` with valid token.
4. Place one test IVR call and verify a new `CA*.json` and audio artifact appears under `data/calls/`.
