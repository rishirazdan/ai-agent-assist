from __future__ import annotations

import datetime
from typing import Dict


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
        parts = [f"{k}={v}" for k, v in d.items()]
        print(" | ".join(parts))
