"""The ONLY module that talks to Ollama (SPEC section 7; swap seam for vLLM etc.).

Tests and offline runs inject any object with the same chat/chat_stream/ping
signatures; the agent loop depends on this interface, never on Ollama.
"""

import json
from dataclasses import dataclass
from typing import Callable

import httpx


@dataclass
class ChatResult:
    text: str
    eval_count: int = 0
    eval_duration_s: float = 0.0
    prompt_eval_count: int = 0


class LLMError(Exception):
    pass


class OllamaLLM:
    def __init__(self, url: str, model: str, timeout_s: float = 120.0, num_ctx: int = 32768):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        # explicit context window: full-context mode (ADR-0012) silently
        # overflows Ollama's default num_ctx otherwise
        self.num_ctx = num_ctx

    def ping(self) -> str:
        """Return 'ok' or an error string (never raises). Used by /api/healthz."""
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=5.0)
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
            if not any(n == self.model or n.startswith(self.model) for n in names):
                return f"model {self.model} not found in ollama"
            return "ok"
        except Exception as e:  # noqa: BLE001 - health probe reports, never raises
            return f"unreachable: {e}"

    def chat(self, messages: list[dict], *, json_format: bool = False, thinking: bool = False) -> ChatResult:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": thinking,
            "options": {"num_ctx": self.num_ctx},
        }
        if json_format:
            payload["format"] = "json"
        try:
            r = httpx.post(f"{self.url}/api/chat", json=payload, timeout=self.timeout_s)
            r.raise_for_status()
            body = r.json()
        except Exception as e:
            raise LLMError(f"ollama chat failed: {e}") from e
        return ChatResult(
            text=body.get("message", {}).get("content", ""),
            eval_count=body.get("eval_count", 0),
            eval_duration_s=body.get("eval_duration", 0) / 1e9,
            prompt_eval_count=body.get("prompt_eval_count", 0),
        )

    def chat_stream(
        self,
        messages: list[dict],
        *,
        thinking: bool = False,
        on_token: Callable[[str, str], None] = lambda text, kind: None,
    ) -> ChatResult:
        """Stream tokens via on_token(text, kind) where kind is 'report' or 'thinking'."""
        payload = {"model": self.model, "messages": messages, "stream": True, "think": thinking, "options": {"num_ctx": self.num_ctx}}
        text_parts: list[str] = []
        eval_count = 0
        eval_duration_s = 0.0
        prompt_eval_count = 0
        try:
            with httpx.stream("POST", f"{self.url}/api/chat", json=payload, timeout=self.timeout_s) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    msg = rec.get("message", {})
                    if msg.get("thinking"):
                        on_token(msg["thinking"], "thinking")
                    if msg.get("content"):
                        text_parts.append(msg["content"])
                        on_token(msg["content"], "report")
                    if rec.get("done"):
                        eval_count = rec.get("eval_count", 0)
                        eval_duration_s = rec.get("eval_duration", 0) / 1e9
                        prompt_eval_count = rec.get("prompt_eval_count", 0)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"ollama stream failed: {e}") from e
        return ChatResult(
            text="".join(text_parts),
            eval_count=eval_count,
            eval_duration_s=eval_duration_s,
            prompt_eval_count=prompt_eval_count,
        )
