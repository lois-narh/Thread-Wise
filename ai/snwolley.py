"""Thin client for the Snwolley Agent API. The key comes from the environment only."""
import logging
import os
import time
from collections import deque

import requests

log = logging.getLogger("threadwise.ai")
RATE_LIMIT, WINDOW = 5, 60          # API allows 5 requests per minute
_calls = deque()


class AIError(Exception):
    """Message is safe to show the user."""


def _throttle():
    now = time.time()
    while _calls and now - _calls[0] > WINDOW:
        _calls.popleft()
    if len(_calls) >= RATE_LIMIT:
        wait = WINDOW - (now - _calls[0]) + 0.5
        log.info("Client-side throttle: waiting %.0fs", wait)
        time.sleep(wait)
    _calls.append(time.time())


def extract_text(data):
    """The response shape isn't documented, so accept the common ones."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        ch = data.get("choices")
        if isinstance(ch, list) and ch:
            msg = ch[0].get("message") or {}
            return msg.get("content") or ch[0].get("text")
        for k in ("response", "message", "content", "answer", "text", "output", "reply"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, dict):
                t = extract_text(v)
                if t:
                    return t
    return None


def ask(message: str, chat_id: str | None = None, retries: int = 2) -> dict:
    url, key = os.getenv("SNWOLLEY_API_URL"), os.getenv("SNWOLLEY_API_KEY")
    if not url or not key:
        raise AIError("AI is not configured. Set SNWOLLEY_API_URL and SNWOLLEY_API_KEY in .env.")
    body = {"message": message, "stream": False}
    if chat_id:
        body["chat_id"] = chat_id
    for attempt in range(retries + 1):
        _throttle()
        try:
            r = requests.post(url, json=body, timeout=90,
                              headers={"Content-Type": "application/json", "X-API-Key": key})
        except requests.RequestException as e:
            log.error("Snwolley request failed: %s", type(e).__name__)
            raise AIError("Could not reach the AI service. Check your connection and try again.")
        if r.status_code == 429 and attempt < retries:
            wait = min(int(r.headers.get("Retry-After", 20)), 65)
            log.warning("Rate limited, retrying in %ss", wait)
            time.sleep(wait + 1)
            continue
        if r.status_code == 401:
            raise AIError("The AI service rejected the API key. Check SNWOLLEY_API_KEY.")
        if r.status_code == 429:
            raise AIError("The AI service is busy (5 requests per minute). Try again shortly.")
        if not r.ok:
            log.error("Snwolley HTTP %s", r.status_code)
            raise AIError(f"The AI service returned an error ({r.status_code}).")
        data = r.json()
        text = extract_text(data)
        if not text:
            log.error("Unrecognised response keys: %s", list(data) if isinstance(data, dict) else type(data))
            raise AIError("The AI service replied in an unexpected format.")
        return {"text": text.strip(), "chat_id": data.get("chat_id") if isinstance(data, dict) else None}