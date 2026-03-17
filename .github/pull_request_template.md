## Summary
- What problem does this PR solve?
- What changed at a high level?

## Why
- Why is this change needed now?
- User or system impact if not merged.

## Test Plan
- [ ] Local app starts (`uvicorn app.main:app --host 0.0.0.0 --port 8000`)
- [ ] `GET /health` returns 200
- [ ] `GET /env-check` behaves as expected (with/without `ADMIN_TOKEN`)
- [ ] Twilio webhook path tested with at least one call
- [ ] Call artifact generated (`data/calls/CA*.json` and audio file)

## Security / Privacy Checklist
- [ ] No secrets or tokens committed
- [ ] PII redaction behavior verified
- [ ] `.gitignore` still excludes sensitive/generated artifacts

## Docs
- [ ] README/SETUP/ARCHITECTURE updated (if behavior changed)

## Rollback
- Revert this PR if regressions are found in webhook ingestion, transcription, or analysis.
