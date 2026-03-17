from __future__ import annotations

import os
import time
from typing import Dict, Any, List, Tuple

import requests

from .log import Log


def _auth() -> Tuple[str, str, str]:
    """
    Returns (account_sid, username, password) for Twilio API auth.
    Supports:
    - Account SID + API Key SID + API Key Secret (preferred)
    - Account SID + Auth Token (fallback)
    """
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    api_key_sid = os.environ.get("TWILIO_API_KEY_SID")
    api_key_secret = os.environ.get("TWILIO_API_KEY_SECRET")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

    if sid and api_key_sid and api_key_secret:
        return sid, api_key_sid, api_key_secret
    if sid and auth_token:
        return sid, sid, auth_token
    raise RuntimeError(
        "Missing Twilio credentials. Set TWILIO_ACCOUNT_SID and either "
        "(TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET) or TWILIO_AUTH_TOKEN."
    )


def recording_media_url(recording: Dict[str, Any]) -> str:
    """
    Convert Twilio recording resource to downloadable media URL.
    """
    media_url = str(recording.get("media_url", "")).strip()
    if media_url:
        return media_url

    sid = str(recording.get("sid", "")).strip()
    account_sid = str(recording.get("account_sid", "")).strip()
    if sid and account_sid:
        # Twilio recording media is fetched from the Calls/{CallSid}/Recordings path
        # or from the account-level Recordings endpoint.
        return f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Recordings/{sid}"

    uri = str(recording.get("uri", "")).strip()
    if uri:
        base = "https://api.twilio.com"
        if uri.endswith(".json"):
            return base + uri[:-5] + ".mp3"
        return base + uri + ".mp3"
    return ""


def list_recordings(call_sid: str) -> List[Dict[str, Any]]:
    Log.section("Twilio List Recordings")
    account_sid, username, password = _auth()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}/Recordings.json"
    Log.info("Fetching recordings for call")
    try:
        resp = requests.get(url, auth=(username, password), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        recordings = data.get("recordings", [])
        Log.info(f"Found {len(recordings)} recordings")
        return recordings
    except Exception as exc:
        Log.error("Failed to list recordings")
        Log.kv({"stage": "list_recordings", "error": str(exc)})
        raise


def download_recording(recording_url: str, output_path: str) -> str:
    Log.section("Twilio Download Recording")
    _, username, password = _auth()
    base_url = recording_url.strip()
    if base_url.endswith(".mp3"):
        candidate_urls = [base_url, base_url[:-4] + ".wav"]
    elif base_url.endswith(".wav"):
        candidate_urls = [base_url[:-4] + ".mp3", base_url]
    elif base_url.endswith(".json"):
        stem = base_url[:-5]
        candidate_urls = [f"{stem}.mp3", f"{stem}.wav"]
    else:
        candidate_urls = [f"{base_url}.mp3", f"{base_url}.wav"]

    Log.info("Downloading recording audio")
    last_error: Exception | None = None
    for attempt in range(1, 7):
        for url in candidate_urls:
            try:
                with requests.get(url, auth=(username, password), stream=True, timeout=60) as resp:
                    if resp.status_code == 404:
                        last_error = RuntimeError(f"recording media not ready: {url}")
                        continue
                    resp.raise_for_status()
                    save_path = output_path
                    if url.lower().endswith(".wav") and output_path.lower().endswith(".mp3"):
                        save_path = output_path[:-4] + ".wav"
                    elif url.lower().endswith(".mp3") and output_path.lower().endswith(".wav"):
                        save_path = output_path[:-4] + ".mp3"

                    with open(save_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                Log.info(f"Saved audio to {save_path}")
                Log.kv({"stage": "download_recording", "attempt": attempt, "url": url, "save_path": save_path})
                return save_path
            except Exception as exc:
                last_error = exc
        if attempt < 6:
            Log.warn("Recording not ready yet, retrying")
            Log.kv({"stage": "download_recording_retry", "attempt": attempt})
            time.sleep(2)

    Log.error("Failed to download recording")
    Log.kv({"stage": "download_recording", "error": str(last_error) if last_error else "unknown"})
    raise RuntimeError("Failed to download recording media after retries")
