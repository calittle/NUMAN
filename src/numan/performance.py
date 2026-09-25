"""Declarative slow-response performance plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StallingCue:
    text: str
    audio_asset: Path

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("stalling cue text must not be empty")


@dataclass(frozen=True, slots=True)
class StallingPlan:
    """Character-owned content; the runtime decides when to play each line."""

    openers: tuple[StallingCue, ...]
    fillers: tuple[str, ...]
    transition: str
    first_filler_delay_s: float = 2.0
    later_filler_delay_s: tuple[float, float] = (7.0, 19.0)

    def __post_init__(self) -> None:
        if not self.openers or not self.transition.strip():
            raise ValueError("stalling openers and transition must not be empty")
        if self.first_filler_delay_s < 0:
            raise ValueError("stalling delay cannot be negative")
        low, high = self.later_filler_delay_s
        if low < 0 or high < low:
            raise ValueError("invalid filler delay range")


_NIGEL_AUDIO = Path(__file__).resolve().parents[2] / "data/nigel/audio"


NIGEL_STALLING_PLAN = StallingPlan(
    openers=(
        StallingCue("Let me think...", _NIGEL_AUDIO / "let-me-think.wav"),
        StallingCue("One moment...", _NIGEL_AUDIO / "one-moment.wav"),
        StallingCue("Let's see...", _NIGEL_AUDIO / "lets-see.wav"),
        StallingCue("Now then...", _NIGEL_AUDIO / "now-then.wav"),
        StallingCue("Give me a second...", _NIGEL_AUDIO / "give-me-a-second.wav"),
        StallingCue("Interesting...", _NIGEL_AUDIO / "interesting.wav"),
        StallingCue("Hang on...", _NIGEL_AUDIO / "hang-on.wav"),
        StallingCue("Right, let me think...", _NIGEL_AUDIO / "right-let-me-think.wav"),
    ),
    fillers=(
        "I am consulting the coconut telegraph.",
        "These things take time when one lacks opposable thumbs.",
    ),
    transition="Here we go!",
)
