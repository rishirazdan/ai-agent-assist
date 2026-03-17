from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB = re.compile(r"\b(?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12][0-9]|3[01])[\/\-](?:19|20)?\d{2}\b")
_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_PHONE = re.compile(r"\b(?:\+?1[\s\-\.]?)?(?:\(?\d{3}\)?[\s\-\.]?)\d{3}[\s\-\.]?\d{4}\b")
_ADDRESS = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.\-'\s]{2,40}\s(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Drive|Dr|Way|Court|Ct)\b\.?",
    re.IGNORECASE,
)
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def _redact_card_candidates(text: str) -> Tuple[str, int]:
    replacements = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal replacements
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19:
            replacements += 1
            return "[REDACTED_CARD]"
        return raw

    return _CARD_CANDIDATE.sub(repl, text), replacements


def redact_text(text: str) -> Tuple[str, Dict[str, int]]:
    if not text:
        return text, {"total": 0}

    output = text
    stats: Dict[str, int] = {}
    patterns = [
        ("ssn", _SSN, "[REDACTED_SSN]"),
        ("dob", _DOB, "[REDACTED_DOB]"),
        ("email", _EMAIL, "[REDACTED_EMAIL]"),
        ("phone", _PHONE, "[REDACTED_PHONE]"),
        ("address", _ADDRESS, "[REDACTED_ADDRESS]"),
    ]

    total = 0
    for name, pattern, replacement in patterns:
        output, count = pattern.subn(replacement, output)
        stats[name] = count
        total += count

    output, card_count = _redact_card_candidates(output)
    stats["card"] = card_count
    total += card_count
    stats["total"] = total
    return output, stats


def redact_object(value: Any) -> Tuple[Any, Dict[str, int]]:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        merged: Dict[str, int] = {"total": 0}
        result: List[Any] = []
        for item in value:
            redacted_item, stats = redact_object(item)
            result.append(redacted_item)
            for k, v in stats.items():
                merged[k] = merged.get(k, 0) + v
        return result, merged
    if isinstance(value, dict):
        merged = {"total": 0}
        result: Dict[str, Any] = {}
        for k, v in value.items():
            redacted_val, stats = redact_object(v)
            result[k] = redacted_val
            for sk, sv in stats.items():
                merged[sk] = merged.get(sk, 0) + sv
        return result, merged
    return value, {"total": 0}
