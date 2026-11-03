"""FastAPI app: text/voice chat, speech-to-text, per-turn latency log, and the web UI."""
import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import Agent
from .config import ROOT
from .llm import GroqClient, LLMClient, LLMError, RateLimited
from .voice import STTError, transcribe

WEB = ROOT / "web"
LATENCY_LOG = ROOT / "logs" / "latency.jsonl"

app = FastAPI(title="Renter intake agent")
app.mount("/static", StaticFiles(directory=WEB), name="static")
_sessions: dict[str, Agent] = {}
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = GroqClient()
    return _llm


def _agent(session_id: str) -> Agent:
    if session_id not in _sessions:
        _sessions[session_id] = Agent(get_llm())
    return _sessions[session_id]


def log_latency(record: dict) -> None:
    LATENCY_LOG.parent.mkdir(exist_ok=True)
    with LATENCY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **record}) + "\n")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.post("/stt")
async def stt(audio: UploadFile = File(...)) -> dict:
    data = await audio.read()
    if not data:
        raise HTTPException(400, "empty recording")
    try:
        text, ms = transcribe(data, audio.filename or "speech.webm", audio.content_type or "audio/webm")
    except STTError as e:
        raise HTTPException(502, str(e))
    return {"text": text, "stt_ms": round(ms, 1)}


class ChatIn(BaseModel):
    session_id: str = "default"
    text: str
    stt_ms: Optional[float] = None  # set when the text came from /stt


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    agent = _agent(body.session_id)
    try:
        result = agent.turn(body.text, stt_ms=body.stt_ms).to_dict()
    except RateLimited as e:
        raise HTTPException(429, f"LLM rate limited: {e}")
    except LLMError as e:
        raise HTTPException(502, str(e))
    result["turn"] = agent.state.turn
    log_latency({"type": "turn", "session_id": body.session_id, "turn": agent.state.turn, **result["timings"]})
    return result


class TTSTiming(BaseModel):
    session_id: str = "default"
    turn: int
    tts_ms: float  # browser: from speak() until speech starts
    speech_ms: Optional[float] = None  # browser: how long the speech played


@app.post("/latency/tts")
def tts_timing(body: TTSTiming) -> dict:
    log_latency({"type": "tts", **body.model_dump()})
    return {"ok": True}


@app.get("/state/{session_id}")
def state(session_id: str) -> dict:
    return _agent(session_id).state.snapshot()


@app.post("/reset/{session_id}")
def reset(session_id: str) -> dict:
    _sessions.pop(session_id, None)
    return {"ok": True}
