"""API tests with a scripted LLM and a stubbed Whisper call (no network)."""
import json

from fastapi.testclient import TestClient

import app.server as server
from test_grounding import FakeLLM, respond


def setup(monkeypatch, tmp_path, script):
    monkeypatch.setattr(server, "_llm", FakeLLM(script))
    monkeypatch.setattr(server, "_sessions", {})
    monkeypatch.setattr(server, "LATENCY_LOG", tmp_path / "latency.jsonl")
    monkeypatch.setattr(server, "transcribe", lambda data, name, ctype: ("mujhe 2 BHK chahiye", 321.0))
    return TestClient(server.app)


def log(tmp_path):
    return [json.loads(line) for line in (tmp_path / "latency.jsonl").read_text().splitlines()]


def test_voice_turn_logs_stt_llm_and_tts(monkeypatch, tmp_path):
    client = setup(monkeypatch, tmp_path, [
        [("update_profile", {"changes": {"bhk": [2]}, "change_kinds": {"bhk": "new"}})],
        [respond("What's your budget?", asking_for=["budget_max"])],
    ])
    stt = client.post("/stt", files={"audio": ("speech.webm", b"\x1a\x45" * 2000, "audio/webm")}).json()
    assert stt == {"text": "mujhe 2 BHK chahiye", "stt_ms": 321.0}

    r = client.post("/chat", json={"session_id": "s1", "text": stt["text"], "stt_ms": stt["stt_ms"]}).json()
    assert r["reply"] == "What's your budget?" and r["turn"] == 1
    assert r["state"]["profile"]["bhk"] == [2]
    assert r["timings"]["stt_ms"] == 321.0 and r["timings"]["llm_calls"] == 2

    assert client.post("/latency/tts", json={"session_id": "s1", "turn": 1, "tts_ms": 85.5, "speech_ms": 1900}).json() == {"ok": True}
    turn, tts = log(tmp_path)
    assert turn["type"] == "turn" and turn["stt_ms"] == 321.0 and turn["session_id"] == "s1" and turn["turn"] == 1
    assert tts["type"] == "tts" and tts["tts_ms"] == 85.5 and tts["turn"] == 1


def test_empty_recording_rejected(monkeypatch, tmp_path):
    client = setup(monkeypatch, tmp_path, [])
    assert client.post("/stt", files={"audio": ("speech.webm", b"", "audio/webm")}).status_code == 400


def test_index_and_static_served(monkeypatch, tmp_path):
    client = setup(monkeypatch, tmp_path, [])
    assert "Hold to talk" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
