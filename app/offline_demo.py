from __future__ import annotations

import datetime
from pathlib import Path

from dotenv import load_dotenv

from .log import Log
from .openai_client import analyze_transcript
from .redaction import redact_text, redact_object
from .storage import save_call


BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = BASE_DIR / "data" / "sample_transcripts"


def run() -> None:
    Log.section("Offline Demo")
    load_dotenv()
    if not SAMPLES_DIR.exists():
        Log.error("Sample transcripts folder not found")
        Log.kv({"stage": "offline_demo", "path": str(SAMPLES_DIR)})
        return

    files = sorted(SAMPLES_DIR.glob("*.txt"))
    if not files:
        Log.warn("No sample transcripts found")
        return

    for path in files:
        Log.section(f"Analyze {path.name}")
        try:
            raw_transcript = path.read_text(encoding="utf-8")
            transcript, transcript_redaction = redact_text(raw_transcript)
            analysis_raw = analyze_transcript(transcript)
            analysis, analysis_redaction = redact_object(analysis_raw)
            Log.info("PII redaction completed")
            Log.kv(
                {
                    "stage": "offline_pii_redaction",
                    "file": path.name,
                    "transcript_redactions": transcript_redaction.get("total", 0),
                    "analysis_redactions": analysis_redaction.get("total", 0),
                }
            )
            call_sid = f"offline-{path.stem}"
            payload = {
                "call_sid": call_sid,
                "source": "offline_demo",
                "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "transcript": transcript,
                "analysis": analysis,
            }
            save_call(call_sid, payload)
        except Exception as exc:
            Log.error("Offline analysis failed")
            Log.kv({"stage": "offline_demo_item", "file": path.name, "error": str(exc)})

    Log.info("Offline demo completed")


if __name__ == "__main__":
    run()
