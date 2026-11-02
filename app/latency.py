"""Per-turn latency breakdown. STT/TTS are filled in by the voice layer (None in text mode)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TurnTimings:
    stt_ms: Optional[float] = None
    llm_ms: float = 0.0  # summed over all LLM calls in the turn
    llm_calls: int = 0
    tool_ms: float = 0.0
    tts_ms: Optional[float] = None
    total_ms: float = 0.0  # agent time (LLM + tools + overhead); the UI adds STT/TTS

    def to_dict(self) -> dict:
        r = lambda v: None if v is None else round(v, 1)
        return {"stt_ms": r(self.stt_ms), "llm_ms": r(self.llm_ms), "llm_calls": self.llm_calls,
                "tool_ms": r(self.tool_ms), "tts_ms": r(self.tts_ms), "total_ms": r(self.total_ms)}
