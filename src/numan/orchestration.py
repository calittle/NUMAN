"""Dispatch-to-actor orchestration with stage-level diagnostics."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter_ns

from .actors import ActorRegistry
from .conversations import ConversationKey, InMemoryConversationStore, TurnRole
from .engine.dispatch import DispatchTrace, Dispatcher
from .engine.models import Character, ResponsePlan, Utterance
from .voice import AudioAsset, VoiceProvider
from .show_control import (
    NullShowControlProvider,
    ScheduledShowCue,
    ShowAction,
    ShowActionScheduler,
    ShowControlProvider,
)
from .performance import StallingPlan


@dataclass(frozen=True, slots=True)
class PerformanceTimings:
    transcription_ms: float
    dispatch_ms: float
    llm_first_token_ms: float
    llm_total_ms: float
    synthesis_ms: float
    queue_wait_ms: float
    answer_start_ms: float
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
    scheduled_actions: tuple[ScheduledShowCue, ...]
    timings: PerformanceTimings


class Orchestrator:
    def __init__(
        self,
        dispatcher: Dispatcher,
        voice: VoiceProvider,
        actors: ActorRegistry,
        conversations: InMemoryConversationStore | None = None,
        show_control: ShowControlProvider | None = None,
        show_scheduler: ShowActionScheduler | None = None,
        stalling: StallingPlan | Mapping[str, StallingPlan] | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._voice = voice
        self._actors = actors
        self._conversations = conversations or InMemoryConversationStore()
        provider = show_control or NullShowControlProvider()
        self._show_scheduler = show_scheduler or ShowActionScheduler(provider)
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

    async def perform_audio(
        self,
        audio: Path,
        transcribe: Callable[[Path], Awaitable[str]],
        character: Character,
        actor_id: str,
        conversation_id: str,
        on_transcript: Callable[[str], None] | None = None,
    ) -> PerformanceResult:
        """Cover transcription with one cached opener, then queue the answer."""
        started = perf_counter_ns()
        actor = self._actors.get(actor_id)
        if actor.character_id != character.id:
            raise ValueError(f"actor {actor.id!r} does not represent {character.id!r}")
        opener = self._stall_asset(character.id)
        opener_task = (
            asyncio.create_task(actor.speak(AudioAsset(opener, owned=False)))
            if opener is not None else None
        )
        try:
            transcription_started = perf_counter_ns()
            transcript = await transcribe(audio)
            transcription_ms = _elapsed(transcription_started)
            if on_transcript is not None:
                on_transcript(transcript)
            result = await self.perform(
                Utterance(transcript, character.id, conversation_id),
                character, actor_id, opener_task=opener_task,
            )
            return replace(
                result,
                timings=replace(
                    result.timings,
                    transcription_ms=transcription_ms,
                    answer_start_ms=transcription_ms + result.timings.answer_start_ms,
                    total_ms=_elapsed(started),
                ),
            )
        finally:
            if opener_task is not None:
                if not opener_task.done():
                    opener_task.cancel()
                # Retrieve failures and finish cancellation even if transcription fails.
                await asyncio.gather(opener_task, return_exceptions=True)

    async def perform(
        self,
        utterance: Utterance,
        character: Character,
        actor_id: str,
        *,
        opener_task: asyncio.Task | None = None,
    ) -> PerformanceResult:
        started = perf_counter_ns()
        actor = self._actors.get(actor_id)
        if actor.character_id != character.id:
            raise ValueError(f"actor {actor.id!r} does not represent {character.id!r}")

        conversation_key = ConversationKey(character.id, utterance.conversation_id)
        await self._conversations.append(conversation_key, TurnRole.USER, utterance.text)
        stall_task: asyncio.Task | None = opener_task

        def on_rule_start(rule_name: str) -> None:
            nonlocal stall_task
            if rule_name == "llm_fallback" and stall_task is None:
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

        if trace.plan.text_stream is not None:
            streamed = await self._perform_stream(
                trace.plan.text_stream, character.voice_profile, actor, stall_task, started
            )
            final_plan = replace(trace.plan, text=streamed["text"], text_stream=None)
            trace = replace(trace, plan=final_plan)
            await self._conversations.append(
                conversation_key, TurnRole.ASSISTANT, final_plan.text
            )
            return PerformanceResult(
                plan=final_plan,
                dispatch_trace=trace,
                actor_id=actor.id,
                route_id=streamed["route_id"],
                played=streamed["played"],
                stall_played=streamed["stall_played"],
                scheduled_actions=(),
                timings=PerformanceTimings(
                    transcription_ms=0.0,
                    dispatch_ms=dispatch_ms,
                    llm_first_token_ms=streamed["llm_first_token_ms"],
                    llm_total_ms=streamed["llm_total_ms"],
                    synthesis_ms=streamed["synthesis_ms"],
                    queue_wait_ms=streamed["queue_wait_ms"],
                    answer_start_ms=streamed["answer_start_ms"],
                    playback_ms=streamed["playback_ms"],
                    total_ms=_elapsed(started),
                ),
            )

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

        playback_requested_ms = _elapsed(started)
        playback_started = perf_counter_ns()
        playback = await actor.speak(asset)
        playback_ms = _elapsed(playback_started)
        scheduled_actions = []
        action_parameters = {
            key: trace.plan.metadata[key]
            for key in ("drink", "intent")
            if key in trace.plan.metadata
        }
        for action_name in trace.plan.show_actions:
            scheduled_actions.append(await self._show_scheduler.schedule(
                ShowAction(action_name, action_parameters),
                character_id=character.id,
                conversation_id=utterance.conversation_id,
                delay_seconds=trace.plan.show_action_delays.get(action_name, 0),
                cooldown_seconds=trace.plan.show_action_cooldowns.get(action_name, 0),
            ))
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
            scheduled_actions=tuple(scheduled_actions),
            timings=PerformanceTimings(
                transcription_ms=0.0,
                dispatch_ms=dispatch_ms,
                llm_first_token_ms=0.0,
                llm_total_ms=0.0,
                synthesis_ms=synthesis_ms,
                queue_wait_ms=playback.queue_wait_ms,
                answer_start_ms=playback_requested_ms + playback.queue_wait_ms,
                playback_ms=playback_ms,
                total_ms=_elapsed(started),
            ),
        )

    async def _perform_stream(
        self, text_stream, profile_id: str, actor, stall_task, started_ns: int
    ) -> dict[str, object]:
        phrase_queue: asyncio.Queue = asyncio.Queue()
        asset_queue: asyncio.Queue = asyncio.Queue()
        state = {
            "text": "",
            "llm_first_token_ms": 0.0,
            "llm_total_ms": 0.0,
            "synthesis_ms": 0.0,
            "queue_wait_ms": 0.0,
            "answer_start_ms": 0.0,
            "playback_ms": 0.0,
            "route_id": "",
            "played": False,
            "stall_played": False,
        }

        async def produce() -> None:
            llm_started = perf_counter_ns()
            buffer = ""
            fragments = []
            first = True
            async for fragment in text_stream:
                if first:
                    state["llm_first_token_ms"] = _elapsed(llm_started)
                    first = False
                fragments.append(fragment)
                buffer += fragment
                phrases, buffer = _complete_phrases(buffer)
                for phrase in phrases:
                    await phrase_queue.put(phrase)
            if buffer.strip():
                await phrase_queue.put(buffer.strip())
            state["text"] = "".join(fragments).strip()
            state["llm_total_ms"] = _elapsed(llm_started)
            await phrase_queue.put(None)

        async def synthesize() -> None:
            while (phrase := await phrase_queue.get()) is not None:
                synthesis_started = perf_counter_ns()
                asset = await self._voice.synthesize(phrase, profile_id)
                state["synthesis_ms"] += _elapsed(synthesis_started)
                await asset_queue.put(asset)
            await asset_queue.put(None)

        async def play() -> None:
            first = True
            while (asset := await asset_queue.get()) is not None:
                if first and stall_task is not None:
                    state["stall_played"] = (await stall_task).played
                requested_ms = _elapsed(started_ns)
                playback_started = perf_counter_ns()
                result = await actor.speak(asset)
                state["playback_ms"] += _elapsed(playback_started)
                state["queue_wait_ms"] += result.queue_wait_ms
                if first:
                    state["answer_start_ms"] = requested_ms + result.queue_wait_ms
                    first = False
                state["route_id"] = result.route_id
                state["played"] = state["played"] or result.played

        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(produce())
            tasks.create_task(synthesize())
            tasks.create_task(play())
        if not state["text"]:
            raise ValueError("streaming response produced no text")
        return state


def _elapsed(started_ns: int) -> float:
    return (perf_counter_ns() - started_ns) / 1_000_000


def _complete_phrases(buffer: str) -> tuple[list[str], str]:
    """Release complete spoken sentences while retaining an unfinished tail."""
    phrases = []
    start = 0
    for index, character in enumerate(buffer):
        if character not in ".!?":
            continue
        end = index + 1
        if end == len(buffer) or buffer[end].isspace():
            phrase = buffer[start:end].strip()
            if phrase:
                phrases.append(phrase)
            start = end
    return phrases, buffer[start:].lstrip()
