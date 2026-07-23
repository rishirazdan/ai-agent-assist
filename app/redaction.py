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
_ZIP_CONTEXTUAL = re.compile(
    r"(?i)\b(?:zip(?:\s*code)?|postal(?:\s*code)?)\b[^\n]{0,24}\b(\d{5}(?:-\d{4})?)\b"
)
_ZIP_AFTER_NAME_LINE = re.compile(r"(?m)\bCaller:\s*[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\s*,\s*(\d{5}(?:-\d{4})?)\b")
_ZIP_AFTER_STATE = re.compile(r",\s*[A-Z]{2}\s+(\d{5}(?:-\d{4})?)\b")
_SSN_LAST4_CONTEXTUAL = re.compile(r"(?is)\b(?:ssn|social\s+security(?:\s+number)?)\b[\s\S]{0,40}?\b(\d{4})\b")
_LAST4_HINT_CONTEXTUAL = re.compile(r"(?is)\b(?:last\s*four(?:\s*digits?)?|last\s*4(?:\s*digits?)?)\b[\s\S]{0,24}?\b(\d{4})\b")
_NAME_CONTEXTUAL_PATTERNS = [
    re.compile(
        r"\b(?i:(?:my\s+name\s+is|name\s+is|i\s+am|it's|it\s+is|this\s+is))\s+"
        r"([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2})\b"
    ),
    re.compile(
        r"\b(?i:(?:caller|customer|account\s+holder))\b\s*[:,-]?\s*"
        r"([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2})\b"
    ),
]


def _redact_contextual_group(text: str, pattern: re.Pattern[str], replacement: str) -> Tuple[str, int]:
    replacements = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal replacements
        group_start, group_end = match.span(1)
        match_start = match.start()
        local_start = group_start - match_start
        local_end = group_end - match_start
        replacements += 1
        matched = match.group(0)
        return matched[:local_start] + replacement + matched[local_end:]

    return pattern.sub(repl, text), replacements


def _redact_contextual_names(text: str) -> Tuple[str, int]:
    output = text
    replacements = 0
    for pattern in _NAME_CONTEXTUAL_PATTERNS:
        output, count = _redact_contextual_group(output, pattern, "[REDACTED_NAME]")
        replacements += count
    return output, replacements


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

    output, count = _redact_contextual_group(output, _SSN_LAST4_CONTEXTUAL, "[REDACTED_SSN_LAST4]")
    stats["ssn_last4"] = count
    total += count

    output, count = _redact_contextual_group(output, _LAST4_HINT_CONTEXTUAL, "[REDACTED_SSN_LAST4]")
    stats["ssn_last4_hint"] = count
    total += count

    output, count = _redact_contextual_group(output, _ZIP_CONTEXTUAL, "[REDACTED_ZIP]")
    stats["zip"] = count
    total += count

    output, count = _redact_contextual_group(output, _ZIP_AFTER_NAME_LINE, "[REDACTED_ZIP]")
    stats["zip_after_name"] = count
    total += count

    output, count = _redact_contextual_group(output, _ZIP_AFTER_STATE, "[REDACTED_ZIP]")
    stats["zip_after_state"] = count
    total += count

    output, count = _redact_contextual_names(output)
    stats["name"] = count
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
