"""Character-owned dispatch policy, separate from physical actors."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoutinePolicy:
    name: str
    pattern: re.Pattern[str]
    pool: str | None = None
    response_template: str | None = None


@dataclass(frozen=True, slots=True)
class CharacterDispatchPolicy:
    character_id: str
    routines: tuple[RoutinePolicy, ...]
