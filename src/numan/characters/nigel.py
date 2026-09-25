"""Nigel character identity and fast-first dispatch policy.

This is not a wholesale migration of Nigel's content. It establishes where
character identity belongs while behavioral parity is built incrementally.
"""

import re

from numan.engine.models import Character
from numan.engine.policy import CharacterDispatchPolicy, RoutinePolicy

NIGEL = Character(
    id="nigel",
    name="Nigel",
    system_prompt=(
        "You are Nigel, a snarky, grizzled old pirate parrot with a gruff "
        "exterior and a loyal, soft heart. Your taunts are sharp, barbed, and "
        "often pun-laden, but never cruel. Answer conversationally and briefly. "
        "Never invent cocktail ingredients "
        "or recipes; ask for clarification when a drink name is uncertain."
    ),
    voice_profile="nigel-edge-ryan-shrill",
    available_show_actions=frozenset(),
    metadata={"compatibility_source": "nigel"},
)


def _pattern(value: str) -> re.Pattern[str]:
    return re.compile(value, re.IGNORECASE)


# Order matches Nigel's routine precedence. Hardware-only introduction and
# impersonation routines are deferred until actors exist; these entries cover
# the text-producing rules that belong in the engine.
NIGEL_DISPATCH_POLICY = CharacterDispatchPolicy(
    character_id=NIGEL.id,
    routines=(
        RoutinePolicy(
            "make_me",
            _pattern(r"make me (?:(?:a|an) )?(?P<thing>.+)$"),
            response_template="Pooooof! You are a {thing}",
        ),
        RoutinePolicy(
            "parrot_taunt",
            _pattern(
                r"polly.*(?:cracker|want)|cracker.*polly|can.*(?:fly|dance|sing|talk|swim)|"
                r"say.*pretty.*bird|are.*you.*(?:parrot|pirate|mascot)|want.*(?:cracker|nut|seed)|"
                r"good.*bird|bad.*bird|whistle|step.*up|spin|go.*(?:crackers|nuts)"
            ),
            pool="_parrot_taunts",
        ),
        RoutinePolicy(
            "greeting",
            _pattern(
                r"^(?:hello|hey|hi|howdy|yo|sup|greetings|good (?:morning|afternoon|evening))|"
                r"how (?:are|is).*(?:you|it)|how.*going|what.s.up|nice to (?:meet|see).*you"
            ),
            pool="_greetings",
        ),
        RoutinePolicy(
            "origin_story",
            _pattern(
                r"where.*(?:are.*you|you.*from|is.*home|do.*come.*from|is.*kalapu|is.*the.*island)|"
                r"kalapu.*atoll|home.*island|born|hatched"
            ),
            pool="_origin_stories",
        ),
        RoutinePolicy(
            "tiki_fact",
            _pattern(
                r"tiki.*(?:fact|trivia|story|history|knowledge|lore|info)|"
                r"(?:interesting|cool|fun).*fact|fact.*(?:about.*tiki|about.*rum|about.*cocktail)"
            ),
            pool="_tiki_facts",
        ),
        RoutinePolicy(
            "tiki_tall_tale",
            _pattern(
                r"tiki.*(?:tall.tale|lie|lies|made.up|nonsense|rubbish|baloney|fiction)|"
                r"tall.tale|make.*up.*(?:fact|story|tiki)|tell.*(?:a.*lie|porky.pie|whopper)"
            ),
            pool="_tiki_tall_tales",
        ),
        RoutinePolicy(
            "bartender_chat",
            _pattern(
                r"bartender.chat|bar.banter|how.s?.*(?:business|the.bar|the.night)|"
                r"(?:busy|slow).*night|chat.with.me|talk.to.me.bartender"
            ),
            pool="_bartender_chat",
        ),
    ),
)
