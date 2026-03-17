# Contributing

Thanks for contributing.

## Scope

This repo is a PoC optimized for clarity and demo reliability. Keep changes small, testable, and easy to review.

## Development Workflow

1. Create a branch per change.
2. Run local checks:
   - `python -m app.offline_demo`
   - `python scripts/qa_regression.py`
3. Validate endpoints:
   - `/health`
   - `/env-check`
   - `/calls`
4. Open PR with:
   - problem statement
   - change summary
   - test evidence (commands + result)

## Coding Expectations

- Follow existing logging pattern in `app/log.py`:
  - `Log.section`, `Log.info/warn/error`, `Log.kv`
- Preserve redaction behavior in `app/redaction.py`.
- Avoid storing secrets in repo files.
- Prefer explicit error context in webhook/transcription paths.

## Documentation Expectations

When behavior changes, update:

- `README.md` for user-facing quickstart/overview
- `SETUP.md` for runbook changes
- `ARCHITECTURE.md` for design/flow changes

## Troubleshooting for Contributors

- OpenAI `429 insufficient_quota`:
  - verify platform API billing and project budget
- Twilio `401`:
  - verify account SID + API key/secret
- No live call artifacts:
  - verify callback URL points to currently running tunnel
