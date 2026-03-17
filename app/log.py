from __future__ import annotations

import datetime
import re
from typing import Dict

_PII_SCRUB = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"  # SSN
    r"|\b(?:\d[ -]*){13,19}\b"  # Card-like
    r"|\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"  # Email
)


def _scrub(value: object) -> str:
    return _PII_SCRUB.sub("[LOG-REDACTED]", str(value))


class Log:
    @staticmethod
    def section(title: str) -> None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n===== {title.upper()} ===== [{ts}]")

    @staticmethod
    def info(msg: str) -> None:
        print(f"[INFO] {msg}")

    @staticmethod
    def warn(msg: str) -> None:
        print(f"[WARN] {msg}")

    @staticmethod
    def error(msg: str) -> None:
        print(f"[ERROR] {msg}")

    @staticmethod
    def kv(d: Dict[str, object]) -> None:
        parts = [f"{k}={_scrub(v)}" for k, v in d.items()]
        print(" | ".join(parts))
