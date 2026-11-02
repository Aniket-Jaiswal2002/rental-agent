"""FastAPI app. Phase 1: /chat, /state, /reset. (Voice and the web UI arrive in phases 2-3.)"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agent import Agent
from .llm import GroqClient, LLMClient, LLMError, RateLimited

app = FastAPI(title="Renter intake agent")
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


class ChatIn(BaseModel):
    session_id: str = "default"
    text: str


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    try:
        return _agent(body.session_id).turn(body.text).to_dict()
    except RateLimited as e:
        raise HTTPException(429, f"LLM rate limited: {e}")
    except LLMError as e:
        raise HTTPException(502, str(e))


@app.get("/state/{session_id}")
def state(session_id: str) -> dict:
    return _agent(session_id).state.snapshot()


@app.post("/reset/{session_id}")
def reset(session_id: str) -> dict:
    _sessions.pop(session_id, None)
    return {"ok": True}
