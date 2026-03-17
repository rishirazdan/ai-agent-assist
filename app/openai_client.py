from __future__ import annotations

import json
import os
import re
from typing import Dict, Any, List

from openai import OpenAI

from .log import Log


def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def transcribe_audio(audio_path: str) -> str:
    Log.section("OpenAI Transcription")
    if os.environ.get("OPENAI_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        Log.warn("OPENAI_DRY_RUN enabled, returning placeholder transcription")
        Log.kv({"stage": "transcribe_audio", "audio_path": audio_path})
        return "Transcription skipped in dry-run mode."

    model = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    Log.info(f"Transcribing audio with model={model}")
    try:
        client = _client()
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model=model,
                file=f,
            )
        text = resp.text or ""
        Log.info("Transcription completed")
        return text
    except Exception as exc:
        Log.error("Transcription failed")
        Log.kv({"stage": "transcribe_audio", "error": str(exc)})
        raise


def _contains_any(text: str, words: List[str]) -> bool:
    return any(word in text for word in words)


def _default_analysis(transcript: str) -> Dict[str, Any]:
    """
    Deterministic fallback for offline/demo mode when API calls fail
    or when OPENAI_DRY_RUN is enabled.
    """
    Log.section("Fallback Analysis")
    lower = transcript.lower()
    positive_hits = sum(
        1
        for w in ["thank", "helpful", "resolved", "great", "appreciate", "understood", "done", "confirmed"]
        if w in lower
    )
    negative_hits = sum(
        1
        for w in ["angry", "upset", "frustrated", "cancel", "fraud", "stolen", "dispute", "did not make"]
        if w in lower
    )

    sentiment = "neutral"
    rationale = "Mixed or limited sentiment indicators in transcript."
    if positive_hits >= negative_hits + 2:
        sentiment = "positive"
        rationale = "Transcript includes more positive resolution language than concern language."
    elif negative_hits >= positive_hits + 2:
        sentiment = "negative"
        rationale = "Transcript includes more concern language than resolution language."

    scores = {
        "greeting": 3,
        "verification": 3,
        "understanding": 3,
        "empathy": 3,
        "clarity": 3,
        "resolution": 3,
        "compliance": 3,
        "overall": 3,
    }

    has_greeting = _contains_any(lower, ["thank you for calling", "thanks for calling", "welcome to"])
    has_verification = _contains_any(lower, ["verify", "date of birth", "last four", "ssn", "security"])
    has_empathy = _contains_any(lower, ["sorry", "understand", "i can help", "happy to help"])
    has_resolution = _contains_any(lower, ["done", "resolved", "blocked", "replacement", "case note", "anything else"])
    has_next_steps = _contains_any(lower, ["5 to 7 business days", "next", "will arrive", "call us right away"])
    has_compliance = _contains_any(lower, ["for security", "verified"])

    if has_greeting:
        scores["greeting"] = 4
    if has_verification:
        scores["verification"] = 4
    if has_empathy:
        scores["empathy"] = 4
    if has_resolution:
        scores["resolution"] = 4
    if has_next_steps:
        scores["clarity"] = 4
    if has_compliance:
        scores["compliance"] = 4
    if _contains_any(lower, ["fraud", "dispute", "lost", "stolen"]) and not has_verification:
        scores["compliance"] = 2

    scores["overall"] = max(1, min(5, round(sum(scores.values()) / len(scores))))

    transcript_lines: List[str] = [line.strip() for line in transcript.splitlines() if line.strip()]
    short_summary = transcript_lines[0][:180] if transcript_lines else "No transcript content."
    long_summary = (
        "Auto-generated fallback summary: "
        + " ".join(transcript_lines[:2])[:500]
        if transcript_lines
        else "Auto-generated fallback summary. No transcript content."
    )

    strengths: List[str] = []
    if has_verification:
        strengths.append("Agent followed an identity verification step.")
    if has_resolution:
        strengths.append("Agent provided a concrete resolution path.")
    if has_next_steps:
        strengths.append("Agent provided clear next-step timing or callback guidance.")
    if not strengths:
        strengths.append("Agent kept the interaction structured and focused.")

    improvements: List[str] = []
    if not has_verification:
        improvements.append("Add explicit identity verification language earlier in the call.")
    if not has_empathy:
        improvements.append("Use empathy phrases before diving into procedural steps.")
    if not has_next_steps:
        improvements.append("Close with explicit next steps and expected timeline.")
    if not improvements:
        improvements.append("Maintain current quality and consistency across calls.")

    return {
        "summary_short": short_summary,
        "summary_long": long_summary,
        "sentiment_overall": sentiment,
        "sentiment_rationale": rationale,
        "scores": scores,
        "strengths": strengths,
        "improvements": improvements,
        "coaching_note": "Keep empathy high and close each call with a concise recap.",
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    content = (text or "").strip()
    if not content:
        raise ValueError("Empty model response")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Handle markdown code fences and mixed output by extracting first JSON object.
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", content, re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(content[start : end + 1])

    raise ValueError("Could not extract JSON object from model response")


def analyze_transcript(transcript: str) -> Dict[str, Any]:
    Log.section("OpenAI Analysis")
    if os.environ.get("OPENAI_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        Log.warn("OPENAI_DRY_RUN enabled, using fallback analysis")
        return _default_analysis(transcript)

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    Log.info(f"Analyzing transcript with model={model}")

    system_prompt = (
        "You are a QA and coaching assistant for a fictional bank call center. "
        "Return strictly valid JSON only, matching the requested schema."
    )

    schema = {
        "summary_short": "string",
        "summary_long": "string",
        "sentiment_overall": "positive|neutral|negative",
        "sentiment_rationale": "string",
        "scores": {
            "greeting": "1-5",
            "verification": "1-5",
            "understanding": "1-5",
            "empathy": "1-5",
            "clarity": "1-5",
            "resolution": "1-5",
            "compliance": "1-5",
            "overall": "1-5",
        },
        "strengths": ["string"],
        "improvements": ["string"],
        "coaching_note": "string",
    }

    user_prompt = (
        "Analyze the following call transcript.\n\n"
        "Return JSON with keys: summary_short, summary_long, sentiment_overall, sentiment_rationale, "
        "scores (greeting, verification, understanding, empathy, clarity, resolution, compliance, overall), "
        "strengths (bullet strings), improvements (bullet strings), coaching_note.\n\n"
        "Scoring scale: 1=poor, 3=average, 5=excellent.\n\n"
        f"Schema example (types only): {json.dumps(schema, ensure_ascii=True)}\n\n"
        "Output strictly valid JSON only. Do not include markdown.\n\n"
        f"Transcript:\n{transcript}"
    )

    try:
        client = _client()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        data = _extract_json_object(content)
        Log.info("Analysis completed")
        return data
    except Exception as exc:
        Log.error("Analysis failed, using fallback")
        Log.kv({"stage": "analyze_transcript", "error": str(exc)})
        return _default_analysis(transcript)
