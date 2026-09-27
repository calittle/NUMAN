"""Captain Grog's fast-first dispatch policy."""

import re

from numan.engine.policy import CharacterDispatchPolicy, RoutinePolicy


def _pattern(value: str) -> re.Pattern[str]:
    return re.compile(value, re.IGNORECASE)


# Hardware-only introduction and impersonation routines are deferred until
# actors exist; these entries cover text-producing rules owned by the engine.
GROG_DISPATCH_POLICY = CharacterDispatchPolicy(
    character_id="grog",
    routines=(
        RoutinePolicy(
            "show_blackout",
            _pattern(r"(?:trigger|start|do|give me|bring on|hit).*(?:blackout|lights out)|(?:blackout|lights out).*(?:now|please)$"),
            pool="_show_blackout",
            show_actions=("blackout",),
        ),
        RoutinePolicy(
            "show_lightning",
            _pattern(r"(?:trigger|start|do|give me|bring on|hit).*(?:lightning|thunderbolt)|(?:lightning|thunderbolt).*(?:now|please)$"),
            pool="_show_lightning",
            show_actions=("lightning",),
        ),
        RoutinePolicy(
            "show_volcano",
            _pattern(r"(?:trigger|start|wake|rumble|give me|bring on).*(?:volcano|mountain)|(?:volcano|mountain).*(?:rumble|now|please)$"),
            pool="_show_volcano",
            show_actions=("volcano_rumble",),
        ),
        RoutinePolicy(
            "show_storm",
            _pattern(r"(?:trigger|start|summon|give me|bring on).*(?:storm|tempest)|(?:storm|tempest).*(?:now|please)$"),
            pool="_show_storm",
            show_actions=("storm",),
        ),
        RoutinePolicy(
            "make_me",
            _pattern(r"make me (?:(?:a|an) )?(?P<thing>.+)$"),
            response_template="A flash of rum-soaked magic, and now you're a {thing}.",
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
