"""Ordered, fast-first response dispatch."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter_ns
from typing import Callable, Protocol

from .models import Character, ResponsePlan, Utterance


class DispatchRule(Protocol):
    """One ordered dispatch layer.

    A rule returns ``None`` on a miss. Rules must not perform playback or
    physical actions; they return a declarative ``ResponsePlan`` instead.
    """

    name: str

    async def evaluate(
        self, utterance: Utterance, character: Character
    ) -> ResponsePlan | None: ...


@dataclass(frozen=True, slots=True)
class DispatchAttempt:
    """One rule evaluation recorded for diagnostics."""

    rule: str
    duration_ms: float
    matched: bool


@dataclass(frozen=True, slots=True)
class DispatchTrace:
    """Explain why a response won and how long each attempted rule took."""

    plan: ResponsePlan
    attempts: tuple[DispatchAttempt, ...]
    total_duration_ms: float

    @property
    def attempted_rules(self) -> tuple[str, ...]:
        return tuple(attempt.rule for attempt in self.attempts)


class Dispatcher:
    """Evaluates rules in declaration order and stops at the first match."""

    def __init__(self, rules: Sequence[DispatchRule]) -> None:
        if not rules:
            raise ValueError("dispatcher requires at least one rule")
        self._rules = tuple(rules)

    @property
    def rule_names(self) -> tuple[str, ...]:
        return tuple(rule.name for rule in self._rules)

    async def dispatch(
        self, utterance: Utterance, character: Character
    ) -> ResponsePlan:
        return (await self.dispatch_with_trace(utterance, character)).plan

    async def dispatch_with_trace(
        self,
        utterance: Utterance,
        character: Character,
        on_rule_start: Callable[[str], None] | None = None,
    ) -> DispatchTrace:
        if utterance.character_id != character.id:
            raise ValueError(
                f"utterance targets {utterance.character_id!r}, "
                f"not character {character.id!r}"
            )

        started = perf_counter_ns()
        attempts: list[DispatchAttempt] = []
        for rule in self._rules:
            if on_rule_start is not None:
                on_rule_start(rule.name)
            rule_started = perf_counter_ns()
            plan = await rule.evaluate(utterance, character)
            elapsed_ms = (perf_counter_ns() - rule_started) / 1_000_000
            attempts.append(DispatchAttempt(rule.name, elapsed_ms, plan is not None))
            if plan is not None:
                if plan.character_id != character.id:
                    raise ValueError(f"rule {rule.name!r} returned the wrong character")
                if plan.conversation_id != utterance.conversation_id:
                    raise ValueError(f"rule {rule.name!r} returned the wrong conversation")
                return DispatchTrace(
                    plan=plan,
                    attempts=tuple(attempts),
                    total_duration_ms=(perf_counter_ns() - started) / 1_000_000,
                )

        raise LookupError("no dispatch rule produced a response")
