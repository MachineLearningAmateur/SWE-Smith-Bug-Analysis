"""Model clients.

One fixed model drives both the injector and the solver:
``qwen/qwen-2.5-coder-32b-instruct`` through OpenRouter. It is a SURROGATE for
the CWM-sft 32B policy used by published SSR, not an exact reproduction; see
``docs/fidelity_limitations.md``.

``ScriptedModel`` replaces the network for tests and for a dry run of the
harness. It is never valid for a corpus run: every generation record carries
the provider name, and the pool reports separate scripted candidates out.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable

from ssr.util import SsrError, get_logger

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cost_usd += other.cost_usd
        self.calls += other.calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "estimated_cost_usd": round(self.cost_usd, 6),
            "calls": self.calls,
        }


@dataclass
class ModelReply:
    text: str
    usage: Usage = field(default_factory=Usage)
    finish_reason: str | None = None


class Model(ABC):
    provider: str = "abstract"
    name: str = "abstract"

    def __init__(self):
        self.total = Usage()

    @abstractmethod
    def _complete(self, messages: list[dict[str, str]]) -> ModelReply:
        ...

    def complete(self, messages: list[dict[str, str]]) -> ModelReply:
        reply = self._complete(messages)
        self.total.add(reply.usage)
        return reply

    def describe(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.name}


class OpenRouterModel(Model):
    """Chat completions over OpenRouter.

    Native function calling is deliberately not requested: the harness uses
    the textual action protocol instead (see ``ssr.action_protocol``).
    """

    provider = "openrouter"

    def __init__(
        self,
        name: str,
        *,
        temperature: float = 0.6,
        top_p: float = 0.95,
        max_tokens: int = 4096,
        retries: int = 4,
        timeout_s: int = 180,
        api_key: str | None = None,
    ):
        super().__init__()
        self.name = name
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.retries = max(1, retries)
        self.timeout_s = timeout_s
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise SsrError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in, "
                "or export the variable. The key is never written to any artifact and is "
                "stripped from every sandbox process."
            )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        referer = os.environ.get("OPENROUTER_APP_URL")
        title = os.environ.get("OPENROUTER_APP_TITLE")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        return headers

    def _complete(self, messages: list[dict[str, str]]) -> ModelReply:
        import requests  # imported here so the package imports without network deps

        payload = {
            "model": self.name,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "usage": {"include": True},
        }
        last_error: str = ""
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(
                    OPENROUTER_URL,
                    headers=self._headers(),
                    data=json.dumps(payload),
                    timeout=self.timeout_s,
                )
            except Exception as exc:  # network layer
                last_error = f"transport error: {exc}"
                self._backoff(attempt, last_error)
                continue

            if response.status_code in (408, 429, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                self._backoff(attempt, last_error)
                continue
            if response.status_code != 200:
                raise SsrError(f"OpenRouter returned HTTP {response.status_code}: {response.text[:1000]}")

            try:
                body = response.json()
            except ValueError as exc:
                last_error = f"non-JSON body: {exc}"
                self._backoff(attempt, last_error)
                continue

            if "error" in body and not body.get("choices"):
                last_error = f"API error: {str(body['error'])[:300]}"
                self._backoff(attempt, last_error)
                continue

            choices = body.get("choices") or []
            if not choices:
                last_error = "no choices in response"
                self._backoff(attempt, last_error)
                continue

            message = choices[0].get("message") or {}
            text = message.get("content") or ""
            usage_body = body.get("usage") or {}
            usage = Usage(
                prompt_tokens=int(usage_body.get("prompt_tokens") or 0),
                completion_tokens=int(usage_body.get("completion_tokens") or 0),
                cost_usd=float(usage_body.get("cost") or 0.0),
                calls=1,
            )
            return ModelReply(text=text, usage=usage, finish_reason=choices[0].get("finish_reason"))

        raise SsrError(f"OpenRouter call failed after {self.retries} attempts: {last_error}")

    def _backoff(self, attempt: int, reason: str) -> None:
        delay = min(60.0, 2.0 ** attempt)
        get_logger().warning("model call attempt %d failed (%s); retrying in %.0fs", attempt, reason, delay)
        time.sleep(delay)


class ScriptedModel(Model):
    """Replays a fixed list of replies. For tests and harness dry runs only."""

    provider = "scripted"

    def __init__(self, replies: Iterable[str], *, name: str = "scripted/deterministic"):
        super().__init__()
        self.name = name
        self._replies = list(replies)
        self._index = 0

    def _complete(self, messages: list[dict[str, str]]) -> ModelReply:
        if self._index >= len(self._replies):
            # Running out of script ends the loop cleanly rather than hanging.
            return ModelReply(
                text="ACTION: FINISH\nSUMMARY: scripted model exhausted",
                usage=Usage(calls=1),
            )
        reply = self._replies[self._index]
        self._index += 1
        return ModelReply(text=reply, usage=Usage(calls=1))


def build_model(config_section: dict[str, Any], *, scripted: list[str] | None = None) -> Model:
    """Build the model named by a ``model:`` config section."""
    if scripted is not None:
        return ScriptedModel(scripted)
    provider = str(config_section.get("provider", "openrouter")).lower()
    if provider != "openrouter":
        raise SsrError(f"unsupported model provider {provider!r}")
    return OpenRouterModel(
        config_section["name"],
        temperature=float(config_section.get("temperature", 0.6)),
        top_p=float(config_section.get("top_p", 0.95)),
        max_tokens=int(config_section.get("max_tokens", 4096)),
        retries=int(config_section.get("request_retries", 4)),
        timeout_s=int(config_section.get("request_timeout_s", 180)),
    )
