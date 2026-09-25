"""Dispatch-to-actor orchestration with stage-level diagnostics."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns

from .actors import ActorRegistry
from .conversations import ConversationKey, InMemoryConversationStore, TurnRole
from .engine.dispatch import DispatchTrace, Dispatcher
from .engine.models import Character, ResponsePlan, Utterance
from .voice import AudioAsset, VoiceProvider
from .show_control import NullShowControlProvider, ShowAction, ShowControlProvider
from .performance import StallingPlan


@dataclass(frozen=True, slots=True)
class PerformanceTimings:
    dispatch_ms: float
    synthesis_ms: float
    queue_wait_ms: float
    playback_ms: float
    total_ms: float


@dataclass(frozen=True, slots=True)
class PerformanceResult:
    plan: ResponsePlan
    dispatch_trace: DispatchTrace
    actor_id: str
    route_id: str
    played: bool
    stall_played: bool
    timings: PerformanceTimings


class Orchestrator:
    def __init__(
        self,
        dispatcher: Dispatcher,
        voice: VoiceProvider,
        actors: ActorRegistry,
        conversations: InMemoryConversationStore | None = None,
        show_control: ShowControlProvider | None = None,
        stalling: StallingPlan | Mapping[str, StallingPlan] | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._voice = voice
        self._actors = actors
        self._conversations = conversations or InMemoryConversationStore()
        self._show_control = show_control or NullShowControlProvider()
        self._stalling = stalling
        self._last_stall_assets: dict[str, Path] = {}

    def _stall_asset(self, character_id: str) -> Path | None:
        plan = (
            self._stalling.get(character_id)
            if isinstance(self._stalling, Mapping)
            else self._stalling
        )
        if plan is None:
            return None
        available = [
            cue.audio_asset for cue in plan.openers if cue.audio_asset.is_file()
        ]
        last = self._last_stall_assets.get(character_id)
        if len(available) > 1 and last in available:
            available.remove(last)
        if not available:
            return None
        selected = random.choice(available)
        self._last_stall_assets[character_id] = selected
        return selected

    async def perform(
        self,
        utterance: Utterance,
        character: Character,
        actor_id: str,
    ) -> PerformanceResult:
        started = perf_counter_ns()
        actor = self._actors.get(actor_id)
        if actor.character_id != character.id:
            raise ValueError(f"actor {actor.id!r} does not represent {character.id!r}")

        conversation_key = ConversationKey(character.id, utterance.conversation_id)
        await self._conversations.append(conversation_key, TurnRole.USER, utterance.text)
        stall_task: asyncio.Task | None = None

        def on_rule_start(rule_name: str) -> None:
            nonlocal stall_task
            if rule_name == "llm_fallback":
                stall_asset = self._stall_asset(character.id)
            else:
                stall_asset = None
            if stall_asset is not None:
                stall_task = asyncio.create_task(
                    actor.speak(AudioAsset(stall_asset, owned=False))
                )

        dispatch_started = perf_counter_ns()
        trace = await self._dispatcher.dispatch_with_trace(
            utterance, character, on_rule_start=on_rule_start
        )
        dispatch_ms = _elapsed(dispatch_started)

        for action_name in trace.plan.show_actions:
            if action_name not in character.available_show_actions:
                raise ValueError(
                    f"character {character.id!r} cannot trigger show action {action_name!r}"
                )
            await self._show_control.trigger(ShowAction(action_name))

        synthesis_started = perf_counter_ns()
        if trace.plan.audio_asset:
            asset = AudioAsset(Path(trace.plan.audio_asset), owned=False)
        elif trace.plan.text:
            asset = await self._voice.synthesize(trace.plan.text, character.voice_profile)
        else:
            raise ValueError("response has no speech or audio for this actor")
        synthesis_ms = _elapsed(synthesis_started)

        stall_played = False
        if stall_task is not None:
            stall_played = (await stall_task).played

        playback_started = perf_counter_ns()
        playback = await actor.speak(asset)
        playback_ms = _elapsed(playback_started)
        if trace.plan.text:
            await self._conversations.append(
                conversation_key, TurnRole.ASSISTANT, trace.plan.text
            )
        return PerformanceResult(
            plan=trace.plan,
            dispatch_trace=trace,
            actor_id=actor.id,
            route_id=playback.route_id,
            played=playback.played,
            stall_played=stall_played,
            timings=PerformanceTimings(
                dispatch_ms=dispatch_ms,
                synthesis_ms=synthesis_ms,
                queue_wait_ms=playback.queue_wait_ms,
                playback_ms=playback_ms,
                total_ms=_elapsed(started),
            ),
        )


def _elapsed(started_ns: int) -> float:
    return (perf_counter_ns() - started_ns) / 1_000_000
