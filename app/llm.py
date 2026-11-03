"""Thin LLM interface plus the Groq adapter (OpenAI-compatible chat completions).

Only Groq is implemented. To add a provider, implement `LLMClient.chat` and return an `LLMResponse`.
The Groq adapter throttles outgoing requests and retries 429s/5xx with exponential backoff.
"""
from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from .config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


class RateLimited(LLMError):
    """Groq kept answering 429 (or asked us to wait too long). Evals report this separately from failures."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: dict = field(default_factory=dict)  # assistant message to append to the transcript
    elapsed_ms: float = 0.0
    retries: int = 0
    total_tokens: int = 0


class LLMClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


class _Throttle:
    """Paces outgoing requests: at least 60/rpm seconds apart, and under `tpm` tokens in any 60s window.

    The token window uses the usage Groq reports for earlier calls and assumes the next call costs about
    as much as the previous one, so we sleep *before* a request instead of retrying into a 429.
    """

    def __init__(self, rpm: int, tpm: int) -> None:
        self.interval = 60.0 / max(rpm, 1)
        self.tpm = tpm
        self._next = 0.0
        self._spent: list[tuple[float, int]] = []  # (monotonic time, tokens)
        self._last_cost = 3000
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            while True:
                now = time.monotonic()
                self._spent = [(t, n) for t, n in self._spent if now - t < 60]
                used = sum(n for _, n in self._spent)
                if not self.tpm or not self._spent or used + self._last_cost <= self.tpm:
                    break
                time.sleep(max(0.5, 60 - (now - self._spent[0][0]) + 0.1))  # until the oldest spend leaves the window
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            time.sleep(delay)

    def record(self, tokens: int) -> None:
        if tokens:
            with self._lock:
                self._spent.append((time.monotonic(), tokens))
                self._last_cost = tokens

class GroqClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.groq_api_key
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set (copy .env.example to .env and add your key)")
        self.model = model or settings.groq_model
        self.throttle = _Throttle(settings.groq_rpm, settings.groq_tpm)
        self.http = httpx.Client(timeout=60)

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "temperature": 0.2,
        }
        if "gpt-oss" in self.model:
            body["reasoning_effort"] = "low"  # keeps reasoning tokens (and latency) down
        headers = {"Authorization": f"Bearer {self.api_key}"}
        started = time.perf_counter()
        retries = 0
        last_429 = False
        while True:
            self.throttle.wait()
            try:
                resp = self.http.post(GROQ_URL, json=body, headers=headers)
            except httpx.TransportError as e:
                resp, err = None, str(e)
            else:
                err = resp.text[:300]

            if resp is not None and resp.status_code == 200:
                parsed = self._parse(resp.json(), (time.perf_counter() - started) * 1000, retries)
                self.throttle.record(parsed.total_tokens)
                return parsed

            status = resp.status_code if resp is not None else 0
            last_429 = status == 429
            if status == 400 and "tool_use_failed" in resp.text:
                # Some models answer in plain text (or bare JSON) instead of a tool call. Hand the text to the
                # agent: it accepts bare JSON only if it validates as a `respond` payload, else re-prompts.
                generated = (resp.json().get("error") or {}).get("failed_generation") or ""
                if generated.strip():
                    return LLMResponse(content=generated, raw_message={"role": "assistant", "content": generated},
                                       elapsed_ms=(time.perf_counter() - started) * 1000, retries=retries)
            # 400 tool_use_failed = the model emitted a malformed tool call; a retry usually fixes it.
            retryable = status in (0, 429, 500, 502, 503, 504) or (status == 400 and "tool_use_failed" in err)
            if not retryable:
                raise LLMError(f"Groq {status}: {err}")
            if retries >= settings.groq_max_retries:
                break
            wait = self._backoff(resp, retries)
            if status == 429 and wait > settings.groq_max_wait_s:
                raise RateLimited(f"Groq asked us to wait {wait:.0f}s (limit {settings.groq_max_wait_s}s): {err}")
            time.sleep(wait)
            retries += 1
        if last_429:
            raise RateLimited(f"still rate limited after {retries} retries: {err}")
        raise LLMError(f"Groq {status} after {retries} retries: {err}")

    @staticmethod
    def _backoff(resp: httpx.Response | None, attempt: int) -> float:
        retry_after = resp.headers.get("retry-after") if resp is not None else None
        if retry_after:
            try:
                return float(retry_after) + random.uniform(0, 0.5)
            except ValueError:
                pass
        return min(2.0**attempt, 30.0) + random.uniform(0, 1.0)  # 1s, 2s, 4s, 8s... plus jitter

    @staticmethod
    def _parse(data: dict, elapsed_ms: float, retries: int) -> LLMResponse:
        msg = data["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            raw_args = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"__invalid_json__": raw_args}
            calls.append(ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=args))
        assistant = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            assistant["tool_calls"] = msg["tool_calls"]
        return LLMResponse(content=msg.get("content") or "", tool_calls=calls, raw_message=assistant,
                           elapsed_ms=elapsed_ms, retries=retries,
                           total_tokens=(data.get("usage") or {}).get("total_tokens", 0))
