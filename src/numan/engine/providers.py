"""Provider boundaries used by dispatch, independent of transport."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, Sequence

from numan.conversations import ConversationTurn
from .models import Character, Utterance


class StructuredDataProvider(Protocol):
    async def lookup(self, query: str, character: Character) -> str | None: ...


class LLMProvider(Protocol):
    async def complete(
        self,
        utterance: Utterance,
        character: Character,
        history: Sequence[ConversationTurn] = (),
    ) -> str: ...


class NullStructuredDataProvider:
    async def lookup(self, query: str, character: Character) -> str | None:
        return None


class FakeLLMProvider:
    """Deterministic provider for tests and pre-integration development."""

    def __init__(self, response: str = "Fake LLM response") -> None:
        self.response = response
        self.calls: list[tuple[Utterance, Character]] = []
        self.histories: list[tuple[ConversationTurn, ...]] = []

    async def complete(self, utterance, character, history=()) -> str:
        self.calls.append((utterance, character))
        self.histories.append(tuple(history))
        return self.response


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    base_url: str
    model: str
    timeout_s: float = 90.0
    keep_alive: str = "8h"


class OllamaLLMProvider:
    """Native adapter for Ollama's local chat API."""

    def __init__(self, config: OllamaConfig) -> None:
        self._config = config

    async def complete(self, utterance, character, history=()) -> str:
        return await asyncio.to_thread(
            self._complete_sync, utterance, character, tuple(history)
        )

    async def stream(self, utterance, character, history=()):
        """Yield native Ollama chat fragments without blocking the event loop."""
        messages = self._messages(utterance, character, tuple(history))
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        finished = object()

        def read_stream() -> None:
            body = {
                "model": self._config.model,
                "messages": messages,
                "stream": True,
                "keep_alive": self._config.keep_alive,
                "options": {"num_predict": 80},
            }
            request = urllib.request.Request(
                f"{self._config.base_url.rstrip('/')}/chat",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self._config.timeout_s
                ) as response:
                    for line in response:
                        if not line.strip():
                            continue
                        payload = json.loads(line)
                        fragment = payload.get("message", {}).get("content", "")
                        if fragment:
                            loop.call_soon_threadsafe(queue.put_nowait, fragment)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, finished)

        task = asyncio.create_task(asyncio.to_thread(read_stream))
        try:
            while True:
                item = await queue.get()
                if item is finished:
                    break
                if isinstance(item, Exception):
                    raise LLMProviderError(f"Ollama streaming request failed: {item}") from item
                yield item
        finally:
            await task

    async def list_models(self) -> tuple[str, ...]:
        return await asyncio.to_thread(self._list_models_sync)

    async def warmup(self) -> None:
        await asyncio.to_thread(
            self._request,
            "generate",
            method="POST",
            body={
                "model": self._config.model,
                "prompt": "",
                "stream": False,
                "keep_alive": self._config.keep_alive,
            },
        )

    def _complete_sync(self, utterance, character, history) -> str:
        messages = self._messages(utterance, character, history)
        payload = self._request(
            "chat",
            method="POST",
            body={
                "model": self._config.model,
                "messages": messages,
                "stream": False,
                "keep_alive": self._config.keep_alive,
                "options": {"num_predict": 80},
            },
        )
        try:
            text = payload["message"]["content"].strip()
        except (KeyError, TypeError, AttributeError) as exc:
            raise LLMProviderError("Ollama returned an invalid chat response") from exc
        if not text:
            raise LLMProviderError("Ollama returned an empty response")
        return text

    @staticmethod
    def _messages(utterance, character, history):
        messages = [{"role": "system", "content": character.system_prompt}]
        messages.extend({"role": turn.role.value, "content": turn.text} for turn in history)
        if not history or history[-1].text != utterance.text:
            messages.append({"role": "user", "content": utterance.text})
        return messages

    def _list_models_sync(self) -> tuple[str, ...]:
        payload = self._request("tags")
        try:
            return tuple(item["name"] for item in payload["models"])
        except (KeyError, TypeError) as exc:
            raise LLMProviderError("Ollama returned an invalid model list") from exc

    def _request(self, path: str, *, method: str = "GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self._config.base_url.rstrip('/')}/{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.timeout_s) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace").strip()
            suffix = f": {detail}" if detail else ""
            raise LLMProviderError(f"Ollama HTTP {exc.code}{suffix}") from exc
        except (OSError, ValueError) as exc:
            raise LLMProviderError(f"cannot reach Ollama at {self._config.base_url}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    endpoint: str
    model: str
    api_key_env: str
    timeout_s: float = 90.0
    max_tokens: int = 160


class OpenAICompatibleLLMProvider:
    """Small HTTP adapter for any OpenAI-compatible chat-completions server."""

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        self._config = config

    async def complete(self, utterance, character, history=()) -> str:
        return await asyncio.to_thread(
            self._complete_sync, utterance, character, tuple(history)
        )

    def _complete_sync(self, utterance, character, history) -> str:
        api_key = os.environ.get(self._config.api_key_env, "").strip()
        if not api_key:
            raise LLMProviderError(
                f"missing API key environment variable: {self._config.api_key_env}"
            )
        messages = [{"role": "system", "content": character.system_prompt}]
        messages.extend({"role": turn.role.value, "content": turn.text} for turn in history)
        if not history or history[-1].text != utterance.text:
            messages.append({"role": "user", "content": utterance.text})
        body = json.dumps({
            "model": self._config.model,
            "messages": messages,
            "max_tokens": self._config.max_tokens,
        }).encode()
        request = urllib.request.Request(
            self._config.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.timeout_s) as response:
                payload = json.load(response)
            text = payload["choices"][0]["message"]["content"].strip()
        except (OSError, urllib.error.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMProviderError(f"LLM request failed: {exc}") from exc
        if not text:
            raise LLMProviderError("LLM returned an empty response")
        return text
