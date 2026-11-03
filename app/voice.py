"""Speech-to-text via Groq Whisper. (Text-to-speech runs in the browser: speechSynthesis.)"""
from __future__ import annotations

import time

import httpx

from .config import settings

STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
# Biases Whisper toward romanised Hinglish and the domain vocabulary instead of Devanagari script.
STT_PROMPT = "Hinglish, Hindi and English mixed, written in Roman script. Gurgaon flat rent, 2 BHK, Sector 56, budget 30 hazaar, Cyber City."


class STTError(RuntimeError):
    pass


def transcribe(audio: bytes, filename: str, content_type: str) -> tuple[str, float]:
    """Return (text, elapsed_ms). One retry on 429/5xx; voice turns are interactive, so no long backoff."""
    if not settings.groq_api_key:
        raise STTError("GROQ_API_KEY is not set")
    data = {"model": settings.stt_model, "prompt": STT_PROMPT, "response_format": "json", "temperature": "0"}
    if settings.stt_language:
        data["language"] = settings.stt_language
    started = time.perf_counter()
    for attempt in range(2):
        resp = httpx.post(STT_URL, headers={"Authorization": f"Bearer {settings.groq_api_key}"}, data=data,
                          files={"file": (filename, audio, content_type)}, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("text", "").strip(), (time.perf_counter() - started) * 1000
        if resp.status_code not in (429, 500, 502, 503) or attempt:
            raise STTError(f"Groq STT {resp.status_code}: {resp.text[:200]}")
        time.sleep(1.5)
    raise STTError("unreachable")
