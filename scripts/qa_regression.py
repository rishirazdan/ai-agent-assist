from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import parse, request, error

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.log import Log
from app.offline_demo import run as run_offline_demo


CALLS_DIR = BASE_DIR / "data" / "calls"
API_BASE = os.environ.get("LOCAL_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert(condition: bool, stage: str, unexpected: str) -> None:
    if not condition:
        Log.error("Regression check failed")
        Log.kv({"stage": stage, "unexpected": unexpected})
        raise AssertionError(f"{stage}: {unexpected}")


def _http_json(method: str, url: str, data: Dict[str, str] | None = None) -> Tuple[int, Dict[str, Any]]:
    payload = None
    headers: Dict[str, str] = {}
    if data is not None:
        payload = parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = request.Request(url=url, method=method, data=payload, headers=headers)
    try:
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except error.HTTPError as http_err:
        body = http_err.read().decode("utf-8")
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"detail": body}
        return int(http_err.code), payload


def check_analysis_schema() -> None:
    Log.section("Check Analysis Schema")
    files = sorted(CALLS_DIR.glob("offline-*.json"))
    _assert(bool(files), "analysis_schema", "no offline call files found")

    required_keys: List[str] = [
        "summary_short",
        "summary_long",
        "sentiment_overall",
        "sentiment_rationale",
        "scores",
        "strengths",
        "improvements",
        "coaching_note",
    ]
    score_keys = ["greeting", "verification", "understanding", "empathy", "clarity", "resolution", "compliance", "overall"]

    for path in files:
        payload = _load_json(path)
        analysis = payload.get("analysis", {})
        missing = [k for k in required_keys if k not in analysis]
        _assert(not missing, "analysis_schema", f"{path.name} missing={missing}")

        scores = analysis.get("scores", {})
        missing_scores = [k for k in score_keys if k not in scores]
        _assert(not missing_scores, "analysis_scores", f"{path.name} missing_scores={missing_scores}")

        invalid_scores = [k for k in score_keys if not isinstance(scores.get(k), int) or not 1 <= scores[k] <= 5]
        _assert(not invalid_scores, "analysis_scores", f"{path.name} invalid_scores={invalid_scores}")

    Log.info(f"Validated analysis schema for {len(files)} files")


def check_pii_redaction() -> None:
    Log.section("Check PII Redaction")
    files = sorted(CALLS_DIR.glob("offline-*.json"))
    _assert(bool(files), "pii_redaction", "no offline call files found")

    patterns = {
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "dob": re.compile(r"\b(?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12][0-9]|3[01])[\/\-](?:19|20)?\d{2}\b"),
        "email": re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
        "phone": re.compile(r"\b(?:\+?1[\s\-\.]?)?(?:\(?\d{3}\)?[\s\-\.]?)\d{3}[\s\-\.]?\d{4}\b"),
        "address": re.compile(
            r"\b\d{1,6}\s+[A-Za-z0-9.\-'\s]{2,40}\s(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Drive|Dr|Way|Court|Ct)\b\.?",
            re.IGNORECASE,
        ),
        "card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    }

    for path in files:
        payload = _load_json(path)
        transcript = str(payload.get("transcript", ""))
        analysis = payload.get("analysis", {})
        twilio_payload = payload.get("twilio", {})
        scan_text = "\n".join(
            [
                transcript,
                str(analysis.get("summary_short", "")),
                str(analysis.get("summary_long", "")),
                str(analysis.get("sentiment_rationale", "")),
                " ".join([str(v) for v in analysis.get("strengths", [])]),
                " ".join([str(v) for v in analysis.get("improvements", [])]),
                str(analysis.get("coaching_note", "")),
                json.dumps(twilio_payload, ensure_ascii=True, sort_keys=True),
            ]
        )

        for name, pattern in patterns.items():
            _assert(
                not pattern.search(scan_text),
                "pii_redaction",
                f"{path.name} contains_unredacted_{name}",
            )

    Log.info(f"Validated PII redaction checks for {len(files)} files")


def check_local_api_paths() -> None:
    Log.section("Check Local API Paths")
    health_status, health_body = _http_json("GET", f"{API_BASE}/health")
    _assert(health_status == 200 and bool(health_body.get("ok")), "api_health", str(health_body))
    Log.info("Health endpoint is reachable")

    no_callsid_status, no_callsid_body = _http_json("POST", f"{API_BASE}/twilio/call-completed", data={})
    no_callsid_error = str(no_callsid_body.get("detail") or no_callsid_body.get("error"))
    _assert(
        no_callsid_status in {400, 200} and no_callsid_error == "Missing CallSid",
        "webhook_missing_callsid",
        str(no_callsid_body),
    )
    Log.info("Webhook missing CallSid guard is working")

    # This validates that webhook returns a controlled error when recording details are missing.
    test_payload = {"CallSid": "CA_REGRESSION_TEST_1"}
    missing_recording_status, missing_recording_body = _http_json(
        "POST",
        f"{API_BASE}/twilio/call-completed",
        data=test_payload,
    )
    _assert(missing_recording_status in {200, 500, 503}, "webhook_missing_recording_status", str(missing_recording_body))
    allowed_errors = {"No recording URL", "processing_failed", "configuration_error"}
    missing_recording_error = str(missing_recording_body.get("detail") or missing_recording_body.get("error"))
    _assert(
        missing_recording_error in allowed_errors,
        "webhook_missing_recording",
        str(missing_recording_body),
    )
    Log.info("Webhook missing recording guard returns controlled error")


def main() -> None:
    Log.section("QA Regression")
    os.environ["OPENAI_DRY_RUN"] = "1"

    Log.section("Run Offline Demo")
    run_offline_demo()

    check_analysis_schema()
    check_pii_redaction()
    check_local_api_paths()
    Log.info("Regression checks completed successfully")


if __name__ == "__main__":
    main()
