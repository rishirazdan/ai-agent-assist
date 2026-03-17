# Revision History

This file tracks major repository milestones to support future GitHub onboarding and clearer review diffs.

## 2026-03-17

- Refreshed documentation set:
  - Updated `README.md`
  - Added `SETUP.md`
  - Added `ARCHITECTURE.md`
  - Added `CONTRIBUTING.md`
  - Added `AGENTS.md`
- Archived legacy architecture narrative into `archive/`.
- Added PII redaction utilities in `app/redaction.py`.
- Wired redaction into live webhook and offline processing paths.
- Added regression checks in `scripts/qa_regression.py`.
- Improved Twilio recording download resilience:
  - media URL fallback handling
  - retry logic for media readiness lag
- Updated Studio Voice IVR (`FW<your_voice_ivr_flow_sid>`) to include recording step before Flex handoff.
- Switched webhook ingress from unstable localtunnel to Cloudflare Tunnel quick URL during testing.

## 2026-03-16

- Established end-to-end PoC flow across Twilio + FastAPI + OpenAI.
- Added architecture PDF export support.
- Implemented fallback analysis behavior for offline/demo mode.

## GitHub Readiness Checklist

Before connecting this repo to GitHub:

1. Rotate all shared secrets used during local testing (OpenAI + Twilio).
2. Add/update `.gitignore` to exclude:
   - `.env`
   - `data/calls/*.mp3`
   - any local transcript artifacts containing customer data
3. Decide whether to keep or remove generated binary artifacts (e.g., PDFs) from source control.
4. Run `python scripts/qa_regression.py` and verify passing output.
5. Confirm docs links/paths are current after any cleanup.
6. Create initial repository labels/milestones if using GitHub Issues/PR workflow.
