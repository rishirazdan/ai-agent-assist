from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, List

from .log import Log


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CALLS_DIR = DATA_DIR / "calls"
CALL_SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def ensure_dirs() -> None:
    CALLS_DIR.mkdir(parents=True, exist_ok=True)


def validate_call_sid(call_sid: str) -> str:
    if not CALL_SID_RE.match(call_sid):
        raise ValueError(f"Invalid call_sid format: {call_sid!r}")
    return call_sid


def call_path(call_sid: str) -> Path:
    safe_call_sid = validate_call_sid(call_sid)
    return CALLS_DIR / f"{safe_call_sid}.json"


def save_call(call_sid: str, payload: Dict[str, Any]) -> None:
    ensure_dirs()
    path = call_path(call_sid)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
    Log.info(f"Saved call data to {path}")


def load_call(call_sid: str) -> Dict[str, Any] | None:
    path = call_path(call_sid)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_calls() -> List[Dict[str, Any]]:
    ensure_dirs()
    calls = []
    for path in sorted(CALLS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            calls.append(data)
        except Exception as exc:
            Log.warn(f"Failed reading {path.name}: {exc}")
    return calls
