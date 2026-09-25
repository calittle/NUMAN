"""Semantic show-control contracts, scheduling, and curated drink cues."""

from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Mapping, Protocol
from uuid import uuid4

from .engine.models import Character, ResponsePlan, ResponseSource, Utterance


@dataclass(frozen=True, slots=True)
class ShowAction:
    name: str
    parameters: Mapping[str, object] = field(default_factory=dict)


class ShowControlProvider(Protocol):
    async def trigger(self, action: ShowAction) -> None: ...


class NullShowControlProvider:
    async def trigger(self, action: ShowAction) -> None:
        return None


class FakeLightORamaProvider:
    """Records semantic requests without implementing LOR choreography."""

    def __init__(self, allowed_actions=()) -> None:
        self.allowed_actions = frozenset(allowed_actions)
        self.triggered: list[ShowAction] = []

    async def trigger(self, action: ShowAction) -> None:
        if action.name not in self.allowed_actions:
            raise ValueError(f"show action is not allowed: {action.name}")
        self.triggered.append(action)


@dataclass(slots=True)
class ScheduledShowCue:
    id: str
    action: ShowAction
    character_id: str
    conversation_id: str
    delay_seconds: float
    status: str
    scheduled_at: datetime
    due_at: datetime
    fired_at: datetime | None = None
    error: str | None = None


class ShowActionScheduler:
    """Non-blocking in-memory scheduler for response-relative show cues."""

    def __init__(self, provider: ShowControlProvider) -> None:
        self._provider = provider
        self._records: dict[str, ScheduledShowCue] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._last_accepted: dict[str, float] = {}

    async def schedule(
        self,
        action: ShowAction,
        *,
        character_id: str,
        conversation_id: str,
        delay_seconds: float = 0,
        cooldown_seconds: float = 0,
    ) -> ScheduledShowCue:
        now = datetime.now(UTC)
        record = ScheduledShowCue(
            id=uuid4().hex,
            action=action,
            character_id=character_id,
            conversation_id=conversation_id,
            delay_seconds=delay_seconds,
            status="scheduled",
            scheduled_at=now,
            due_at=now + timedelta(seconds=delay_seconds),
        )
        key = self._dedupe_key(action)
        last = self._last_accepted.get(key)
        current = monotonic()
        if last is not None and current - last < cooldown_seconds:
            record.status = "suppressed"
            self._records[record.id] = record
            return record
        self._last_accepted[key] = current
        self._records[record.id] = record
        if delay_seconds <= 0:
            await self._fire(record)
        else:
            self._tasks[record.id] = asyncio.create_task(self._run(record))
        return record

    async def _run(self, record: ScheduledShowCue) -> None:
        try:
            await asyncio.sleep(record.delay_seconds)
            await self._fire(record)
        except asyncio.CancelledError:
            if record.status == "scheduled":
                record.status = "cancelled"
            raise
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
        finally:
            self._tasks.pop(record.id, None)

    async def _fire(self, record: ScheduledShowCue) -> None:
        await self._provider.trigger(record.action)
        record.status = "fired"
        record.fired_at = datetime.now(UTC)

    def cancel(self, cue_id: str) -> bool:
        record = self._records.get(cue_id)
        if record is None or record.status != "scheduled":
            return False
        record.status = "cancelled"
        task = self._tasks.get(cue_id)
        if task is not None:
            task.cancel()
        self._last_accepted.pop(self._dedupe_key(record.action), None)
        return True

    def records(self) -> tuple[ScheduledShowCue, ...]:
        return tuple(self._records.values())

    async def shutdown(self) -> None:
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _dedupe_key(action: ShowAction) -> str:
        parameters = json.dumps(dict(action.parameters), sort_keys=True)
        return f"{action.name}:{parameters}"


@dataclass(frozen=True, slots=True)
class DrinkPresentation:
    drink_id: str
    aliases: tuple[str, ...]
    show_action: str
    order_delay_seconds: float
    serving_delay_seconds: float
    cooldown_seconds: float
    responses: Mapping[str, tuple[str, ...]]


class DrinkPresentationCatalog:
    """Validated, local drink cues; LLM output never enters this path."""

    _ORDER = re.compile(
        r"\b(?:i want|i'd like|i would like|give me|make me|can i get|i'll have|order)\b",
        re.IGNORECASE,
    )
    _SERVING = re.compile(
        r"\b(?:i am serving|i'm serving|we are serving|we're serving|now serving|serving)\b",
        re.IGNORECASE,
    )
    _INFORMATION = re.compile(
        r"\b(?:recipe|ingredients?|what(?:'s| is) in|how (?:do|would) (?:you|i) make)\b",
        re.IGNORECASE,
    )

    def __init__(self, path: str | Path) -> None:
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read drink presentations {source}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("drink presentations must be a JSON object")
        self._items = tuple(self._parse(drink_id, item) for drink_id, item in raw.items())

    @property
    def items(self) -> tuple[DrinkPresentation, ...]:
        return self._items

    @staticmethod
    def _parse(drink_id: str, raw: object) -> DrinkPresentation:
        if not isinstance(raw, dict):
            raise ValueError(f"drink presentation {drink_id!r} must be an object")
        responses = raw.get("responses", {})
        if not isinstance(responses, dict):
            raise ValueError(f"drink presentation {drink_id!r} responses must be an object")
        parsed_responses = {
            character_id: tuple(values)
            for character_id, values in responses.items()
            if isinstance(character_id, str)
            and isinstance(values, list)
            and values
            and all(isinstance(value, str) and value.strip() for value in values)
        }
        aliases = raw.get("aliases", [])
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"drink presentation {drink_id!r} requires aliases")
        presentation = DrinkPresentation(
            drink_id=drink_id,
            aliases=tuple(str(alias).casefold() for alias in aliases),
            show_action=str(raw["show_action"]),
            order_delay_seconds=float(raw.get("order_delay_seconds", 0)),
            serving_delay_seconds=float(raw.get("serving_delay_seconds", 0)),
            cooldown_seconds=float(raw.get("cooldown_seconds", 30)),
            responses=parsed_responses,
        )
        if presentation.order_delay_seconds < 0 or presentation.serving_delay_seconds < 0:
            raise ValueError(f"drink presentation {drink_id!r} delays cannot be negative")
        if presentation.cooldown_seconds < 0:
            raise ValueError(f"drink presentation {drink_id!r} cooldown cannot be negative")
        return presentation

    def match(self, text: str, character_id: str) -> tuple[DrinkPresentation, str] | None:
        normalized = " ".join(text.casefold().replace("’", "'").split())
        if self._INFORMATION.search(normalized):
            return None
        intent = (
            "serving" if self._SERVING.search(normalized)
            else "ordering" if self._ORDER.search(normalized)
            else None
        )
        if intent is None:
            return None
        for item in self._items:
            if character_id in item.responses and any(
                re.search(rf"\b{re.escape(alias)}\b", normalized)
                for alias in item.aliases
            ):
                return item, intent
        return None


class DrinkPresentationRule:
    name = "drink_presentation"

    def __init__(self, catalog: DrinkPresentationCatalog, chooser=random.choice) -> None:
        self._catalog = catalog
        self._chooser = chooser

    async def evaluate(self, utterance: Utterance, character: Character):
        match = self._catalog.match(utterance.text, character.id)
        if match is None:
            return None
        presentation, intent = match
        delay = (
            presentation.serving_delay_seconds
            if intent == "serving"
            else presentation.order_delay_seconds
        )
        return ResponsePlan(
            character_id=character.id,
            conversation_id=utterance.conversation_id,
            source=ResponseSource.ROUTINE,
            text=self._chooser(presentation.responses[character.id]),
            show_actions=(presentation.show_action,),
            show_action_delays={presentation.show_action: delay},
            show_action_cooldowns={
                presentation.show_action: presentation.cooldown_seconds
            },
            metadata={
                "routine": "drink_presentation",
                "drink": presentation.drink_id,
                "intent": intent,
            },
        )
