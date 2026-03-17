from __future__ import annotations

import asyncio
import datetime
import base64
import hashlib
import hmac
import html
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from dotenv import load_dotenv

from .log import Log
from .openai_client import transcribe_audio, analyze_transcript
from .redaction import redact_text, redact_object
from .storage import save_call, list_calls, load_call, validate_call_sid
from .twilio_client import list_recordings, download_recording, recording_media_url


BASE_DIR = Path(__file__).resolve().parent.parent
CALLS_DIR = BASE_DIR / "data" / "calls"

load_dotenv()

app = FastAPI()


def _is_true(name: str, default: str = "0") -> bool:
    value = os.environ.get(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _twilio_expected_signature(url: str, payload: Dict[str, Any], auth_token: str) -> str:
    """
    Twilio form webhook signature:
    base64(hmac_sha1(auth_token, url + sorted(key+value)...))
    """
    s = url
    for key in sorted(payload.keys()):
        s += key + str(payload.get(key, ""))
    digest = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def _validate_twilio_signature(request: Request, payload: Dict[str, Any]) -> bool:
    Log.section("Validate Twilio Signature")
    if not _is_true("TWILIO_VALIDATE_SIGNATURE", default="1"):
        Log.info("Signature validation disabled")
        return True

    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    signature = request.headers.get("X-Twilio-Signature", "").strip()
    if not auth_token:
        Log.error("Signature validation enabled but TWILIO_AUTH_TOKEN missing")
        Log.kv({"stage": "signature_validation", "reason": "missing_auth_token"})
        return False
    if not signature:
        Log.error("Missing X-Twilio-Signature header")
        Log.kv({"stage": "signature_validation", "reason": "missing_header"})
        return False

    path_with_query = request.url.path
    if request.url.query:
        path_with_query = f"{path_with_query}?{request.url.query}"

    candidate_urls = [str(request.url)]
    public_base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base:
        candidate_urls.append(f"{public_base}{path_with_query}")

    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").strip()
    forwarded_host = request.headers.get("X-Forwarded-Host", "").strip()
    if forwarded_proto and forwarded_host:
        candidate_urls.append(f"{forwarded_proto}://{forwarded_host}{path_with_query}")

    # Preserve order, remove duplicates.
    deduped_candidate_urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidate_urls:
        if candidate and candidate not in seen:
            deduped_candidate_urls.append(candidate)
            seen.add(candidate)

    is_valid = False
    matched_candidate = ""
    for candidate in deduped_candidate_urls:
        expected = _twilio_expected_signature(candidate, payload, auth_token)
        if hmac.compare_digest(expected, signature):
            is_valid = True
            matched_candidate = candidate
            break

    Log.info("Signature validation completed")
    Log.kv(
        {
            "stage": "signature_validation",
            "valid": is_valid,
            "candidate_count": len(deduped_candidate_urls),
            "matched_public_base": bool(public_base and matched_candidate.startswith(public_base)),
        }
    )
    return is_valid


def _is_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _check_admin_token(request: Request) -> None:
    """
    Optional auth gate for diagnostics endpoints.
    If ADMIN_TOKEN is set, require it via X-Admin-Token header
    or Authorization: Bearer <token>.
    """
    expected = os.environ.get("ADMIN_TOKEN", "").strip()
    if not expected:
        return

    header_token = request.headers.get("X-Admin-Token", "").strip()
    auth = request.headers.get("Authorization", "").strip()
    bearer_token = ""
    if auth.lower().startswith("bearer "):
        bearer_token = auth[7:].strip()

    provided = header_token or bearer_token
    if provided != expected:
        Log.warn("Rejected env-check request with invalid admin token")
        Log.kv({"stage": "env_check", "reason": "unauthorized"})
        raise HTTPException(status_code=401, detail="Unauthorized")


def _process_twilio_call_completed_sync(
    call_sid: str,
    recording_url: str | None,
    payload: Dict[str, Any],
    audio_path: str,
) -> Dict[str, Any]:
    effective_recording_url = recording_url
    if not effective_recording_url:
        recordings = list_recordings(call_sid)
        if recordings:
            effective_recording_url = recording_media_url(recordings[0])

    if not effective_recording_url:
        Log.warn("No recording URL found")
        Log.kv({"stage": "webhook_processing", "reason": "missing_recording_url", "call_sid": call_sid})
        return {"ok": False, "error": "No recording URL"}
    if not str(effective_recording_url).startswith("http"):
        Log.warn("Recording URL is not valid")
        Log.kv(
            {"stage": "webhook_processing", "reason": "invalid_recording_url", "recording_url": effective_recording_url}
        )
        return {"ok": False, "error": "Invalid recording URL"}

    downloaded_audio_path = download_recording(effective_recording_url, audio_path)
    raw_transcript = transcribe_audio(downloaded_audio_path)
    transcript, transcript_redaction = redact_text(raw_transcript)
    analysis_raw = analyze_transcript(transcript)
    analysis, analysis_redaction = redact_object(analysis_raw)
    twilio_payload, payload_redaction = redact_object(payload)
    Log.info("PII redaction completed")
    Log.kv(
        {
            "stage": "pii_redaction",
            "transcript_redactions": transcript_redaction.get("total", 0),
            "analysis_redactions": analysis_redaction.get("total", 0),
            "payload_redactions": payload_redaction.get("total", 0),
        }
    )

    data = {
        "call_sid": call_sid,
        "source": "twilio",
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "twilio": twilio_payload,
        "recording_url": effective_recording_url,
        "transcript": transcript,
        "analysis": analysis,
    }
    save_call(call_sid, data)
    return {"ok": True, "call_sid": call_sid}


@app.get("/")
def root() -> PlainTextResponse:
    Log.section("Service Health")
    Log.info("Health check requested")
    return PlainTextResponse("AI Agent Assist is running. Visit /calls")


@app.get("/health")
def health() -> Dict[str, Any]:
    Log.section("Health Endpoint")
    Log.info("Health status requested")
    return {"ok": True, "service": "ai-agent-assist", "time": datetime.datetime.now(datetime.UTC).isoformat()}


@app.get("/env-check")
def env_check(request: Request) -> Dict[str, Any]:
    """
    Returns presence/shape checks only. Does not return secret values.
    """
    _check_admin_token(request)
    Log.section("Environment Check")
    public_base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    webhook_url = f"{public_base}/twilio/call-completed" if public_base else ""
    checks = {
        "openai_api_key_set": _is_set("OPENAI_API_KEY"),
        "openai_dry_run": _is_true("OPENAI_DRY_RUN"),
        "openai_model_set": _is_set("OPENAI_MODEL"),
        "openai_transcribe_model_set": _is_set("OPENAI_TRANSCRIBE_MODEL"),
        "twilio_account_sid_set": _is_set("TWILIO_ACCOUNT_SID"),
        "twilio_api_key_sid_set": _is_set("TWILIO_API_KEY_SID"),
        "twilio_api_key_secret_set": _is_set("TWILIO_API_KEY_SECRET"),
        "twilio_auth_token_set": _is_set("TWILIO_AUTH_TOKEN"),
        "twilio_validate_signature": _is_true("TWILIO_VALIDATE_SIGNATURE", default="1"),
        "public_base_url_set": bool(public_base),
        "agent_dial_number_set": _is_set("AGENT_DIAL_NUMBER"),
    }
    Log.info("Environment check completed")
    Log.kv(
        {
            "stage": "env_check",
            "openai_key": checks["openai_api_key_set"],
            "twilio_sid": checks["twilio_account_sid_set"],
            "public_base": checks["public_base_url_set"],
        }
    )
    return {"ok": True, "checks": checks, "expected_twilio_webhook": webhook_url}


@app.get("/calls", response_class=HTMLResponse)
def calls_list() -> str:
    Log.section("Render Calls List")
    calls = list_calls()
    rows = []
    for c in calls:
        call_sid = html.escape(c.get("call_sid", ""))
        analysis = c.get("analysis", {})
        summary = html.escape(analysis.get("summary_short", ""))
        sentiment = html.escape(analysis.get("sentiment_overall", ""))
        created_at = html.escape(c.get("created_at", ""))
        rows.append(
            f"<tr><td><a href='/calls/{call_sid}'>{call_sid}</a></td>"
            f"<td>{created_at}</td><td>{sentiment}</td><td>{summary}</td></tr>"
        )

    table = "".join(rows) if rows else "<tr><td colspan='4'>No calls yet.</td></tr>"
    return (
        "<html><head><title>Calls</title></head><body>"
        "<h1>Bank Call Center - Calls</h1>"
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>CallSid</th><th>Created</th><th>Sentiment</th><th>Summary</th></tr>"
        f"{table}"  # nosec B703
        "</table></body></html>"
    )


@app.get("/calls/{call_sid}", response_class=HTMLResponse)
def call_detail(call_sid: str) -> str:
    Log.section("Render Call Detail")
    data = load_call(call_sid)
    if not data:
        return "<html><body><h1>Not found</h1></body></html>"

    analysis = data.get("analysis", {})

    def field(label: str, value: str) -> str:
        return f"<p><strong>{label}:</strong> {html.escape(value)}</p>"

    strengths = "".join(f"<li>{html.escape(s)}</li>" for s in analysis.get("strengths", []))
    improvements = "".join(f"<li>{html.escape(s)}</li>" for s in analysis.get("improvements", []))

    scores = analysis.get("scores", {})
    score_rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in scores.items()
    )

    transcript = html.escape(data.get("transcript", ""))

    return (
        "<html><head><title>Call Detail</title></head><body>"
        f"<h1>Call {html.escape(call_sid)}</h1>"
        f"{field('Created', data.get('created_at', ''))}"
        f"{field('Summary (short)', analysis.get('summary_short', ''))}"
        f"{field('Summary (long)', analysis.get('summary_long', ''))}"
        f"{field('Sentiment', analysis.get('sentiment_overall', ''))}"
        f"{field('Sentiment rationale', analysis.get('sentiment_rationale', ''))}"
        "<h2>Scores</h2>"
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Category</th><th>Score</th></tr>"
        f"{score_rows}"  # nosec B703
        "</table>"
        "<h2>Strengths</h2><ul>"
        f"{strengths}"  # nosec B703
        "</ul>"
        "<h2>Improvements</h2><ul>"
        f"{improvements}"  # nosec B703
        "</ul>"
        f"{field('Coaching note', analysis.get('coaching_note', ''))}"
        "<h2>Transcript</h2>"
        f"<pre style='white-space: pre-wrap'>{transcript}</pre>"
        "<p><a href='/calls'>Back to list</a></p>"
        "</body></html>"
    )


@app.post("/twilio/call-completed")
async def twilio_call_completed(request: Request) -> Dict[str, Any]:
    Log.section("Twilio Webhook")
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        # Twilio voice webhooks are form-encoded; reject JSON to avoid signature bypass.
        Log.warn("Rejected webhook with unsupported JSON content-type")
        Log.kv({"stage": "webhook", "reason": "unsupported_content_type"})
        raise HTTPException(status_code=415, detail="unsupported_content_type")

    form = await request.form()
    payload = dict(form)

    call_sid_raw = payload.get("CallSid")
    recording_url = payload.get("RecordingUrl")
    digits = payload.get("Digits")

    Log.info("Received webhook")
    Log.kv({"stage": "webhook", "call_sid": call_sid_raw or "", "digits": digits or ""})

    if not _validate_twilio_signature(request, payload):
        Log.warn("Rejected webhook with invalid signature")
        raise HTTPException(status_code=403, detail="invalid_signature")

    if not call_sid_raw:
        Log.warn("Missing CallSid in webhook")
        raise HTTPException(status_code=400, detail="Missing CallSid")
    try:
        call_sid = validate_call_sid(str(call_sid_raw))
    except ValueError:
        Log.warn("Rejected webhook with invalid CallSid format")
        Log.kv({"stage": "webhook", "call_sid": str(call_sid_raw)})
        raise HTTPException(status_code=400, detail="Invalid CallSid")

    Log.section("Webhook Idempotency Guard")
    existing_call = load_call(call_sid)
    if existing_call is not None:
        Log.warn("Duplicate webhook ignored")
        Log.kv({"stage": "idempotency_guard", "call_sid": call_sid, "duplicate": True})
        return {"ok": True, "call_sid": call_sid, "duplicate": True}

    CALLS_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = str(CALLS_DIR / f"{call_sid}.mp3")

    try:
        Log.info("Offloading webhook processing to worker thread")
        Log.kv({"stage": "webhook_processing", "call_sid": call_sid})
        result = await asyncio.to_thread(
            _process_twilio_call_completed_sync,
            call_sid,
            str(recording_url) if recording_url else None,
            payload,
            audio_path,
        )
        if not bool(result.get("ok")):
            error = str(result.get("error", "processing_failed"))
            # Missing/invalid recording URL is often transient in Twilio recording lifecycle.
            if error in {"No recording URL", "Invalid recording URL"}:
                raise HTTPException(status_code=503, detail=error)
            raise HTTPException(status_code=500, detail=error)
        return result
    except RuntimeError as exc:
        Log.error("Configuration error during webhook processing")
        Log.kv({"stage": "webhook_processing", "error": str(exc), "call_sid": call_sid})
        raise HTTPException(status_code=500, detail="configuration_error")
    except Exception as exc:
        Log.error("Webhook processing failed")
        Log.kv({"stage": "webhook_processing", "error": str(exc)})
        # Return 503 so Twilio can retry on transient failures.
        raise HTTPException(status_code=503, detail="processing_failed")
