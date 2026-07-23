from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator

from braintrust import Eval

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.openai_client import analyze_transcript


CALLS_DIR = BASE_DIR / "data" / "calls"

REQUIRED_KEYS = [
    "summary_short",
    "summary_long",
    "sentiment_overall",
    "sentiment_rationale",
    "scores",
    "strengths",
    "improvements",
    "coaching_note",
]

SCORE_KEYS = ["greeting", "verification", "understanding", "empathy", "clarity", "resolution", "compliance", "overall"]

PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
    re.compile(r"\b(?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12][0-9]|3[01])[\/\-](?:19|20)?\d{2}\b"),  # DOB
    re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),  # Email
    re.compile(r"\b(?:\+?1[\s\-\.]?)?(?:\(?\d{3}\)?[\s\-\.]?)\d{3}[\s\-\.]?\d{4}\b"),  # Phone
    re.compile(
        r"\b\d{1,6}\s+[A-Za-z0-9.\-'\s]{2,40}\s(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Drive|Dr|Way|Court|Ct)\b\.?",
        re.IGNORECASE,
    ),  # Address
]


def _iter_offline_calls() -> Iterator[Dict[str, Any]]:
    for path in sorted(CALLS_DIR.glob("offline-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        transcript = str(payload.get("transcript", "")).strip()
        if not transcript:
            continue
        yield {
            "input": transcript,
            "expected": payload.get("analysis", {}),
            "metadata": {"file_name": path.name, "call_sid": payload.get("call_sid", "")},
        }


def _task(transcript: str) -> Dict[str, Any]:
    # Default to offline-safe mode unless explicitly opted in to paid OpenAI eval runs.
    if os.environ.get("BT_USE_OPENAI", "").strip().lower() not in {"1", "true", "yes", "on"}:
        os.environ["OPENAI_DRY_RUN"] = "1"
    return analyze_transcript(transcript)


def _schema_score(input: str, output: Dict[str, Any], expected: Dict[str, Any]) -> float:
    if not isinstance(output, dict):
        return 0.0
    missing = [k for k in REQUIRED_KEYS if k not in output]
    return 1.0 if not missing else 0.0


def _score_range_score(input: str, output: Dict[str, Any], expected: Dict[str, Any]) -> float:
    if not isinstance(output, dict):
        return 0.0
    scores = output.get("scores", {})
    if not isinstance(scores, dict):
        return 0.0
    valid = 0
    for key in SCORE_KEYS:
        value = scores.get(key)
        if isinstance(value, int) and 1 <= value <= 5:
            valid += 1
    return valid / len(SCORE_KEYS)


def _sentiment_match_score(input: str, output: Dict[str, Any], expected: Dict[str, Any]) -> float:
    expected_sentiment = str(expected.get("sentiment_overall", "")).strip().lower()
    actual_sentiment = str(output.get("sentiment_overall", "")).strip().lower() if isinstance(output, dict) else ""
    if not expected_sentiment:
        return 1.0
    return 1.0 if actual_sentiment == expected_sentiment else 0.0


def _pii_leak_score(input: str, output: Dict[str, Any], expected: Dict[str, Any]) -> float:
    text = json.dumps(output if isinstance(output, dict) else {}, ensure_ascii=True, sort_keys=True)
    for pattern in PII_PATTERNS:
        if pattern.search(text):
            return 0.0
    return 1.0


Eval(
    "AI Agent Assist - Call QA Eval",
    data=_iter_offline_calls,
    task=_task,
    scores=[_schema_score, _score_range_score, _sentiment_match_score, _pii_leak_score],
)
