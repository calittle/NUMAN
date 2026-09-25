"""Polly character identity and initial fast-first policy."""

import re

from numan.engine.policy import CharacterDispatchPolicy, RoutinePolicy


POLLY_DISPATCH_POLICY = CharacterDispatchPolicy(
    character_id="polly",
    routines=(
        RoutinePolicy(
            "show_lightning",
            re.compile(
                r"(?:trigger|start|do|give me|bring on|hit).*(?:lightning|thunderbolt)|"
                r"(?:lightning|thunderbolt).*(?:now|please)$",
                re.IGNORECASE,
            ),
            pool="_show_lightning",
            show_actions=("lightning",),
        ),
        RoutinePolicy(
            "show_storm",
            re.compile(
                r"(?:trigger|start|summon|give me|bring on).*(?:storm|tempest)|"
                r"(?:storm|tempest).*(?:now|please)$",
                re.IGNORECASE,
            ),
            pool="_show_storm",
            show_actions=("storm",),
        ),
        RoutinePolicy(
            "parrot_taunt",
            re.compile(
                r"polly.*(?:cracker|want)|cracker.*polly|can.*(?:fly|dance|sing|talk|swim)|"
                r"say.*pretty.*bird|are.*you.*(?:parrot|pirate|mascot)|want.*(?:cracker|nut|seed)|"
                r"good.*bird|bad.*bird|whistle|step.*up|spin|go.*(?:crackers|nuts)",
                re.IGNORECASE,
            ),
            pool="_parrot_taunts",
        ),
        RoutinePolicy(
            "greeting",
            re.compile(
                r"^(?:hello|hey|hi|howdy|greetings|good (?:morning|afternoon|evening))|"
                r"how (?:are|is).*(?:you|it)|nice to (?:meet|see).*you",
                re.IGNORECASE,
            ),
            pool="_greetings",
        ),
        RoutinePolicy(
            "origin_story",
            re.compile(
                r"where.*(?:are.*you|you.*from|is.*home|do.*come.*from|is.*kalapu|is.*the.*island)|"
                r"kalapu.*atoll|home.*island|born|hatched",
                re.IGNORECASE,
            ),
            pool="_origin_stories",
        ),
        RoutinePolicy(
            "tiki_fact",
            re.compile(
                r"tiki.*(?:fact|trivia|story|history|knowledge|lore|info)|"
                r"(?:interesting|cool|fun).*fact|fact.*(?:about.*tiki|about.*rum|about.*cocktail)",
                re.IGNORECASE,
            ),
            pool="_tiki_facts",
        ),
        RoutinePolicy(
            "tiki_tall_tale",
            re.compile(
                r"tiki.*(?:tall.tale|lie|lies|made.up|nonsense|rubbish|baloney|fiction)|"
                r"tall.tale|make.*up.*(?:fact|story|tiki)|tell.*(?:a.*lie|porky.pie|whopper)",
                re.IGNORECASE,
            ),
            pool="_tiki_tall_tales",
        ),
        RoutinePolicy(
            "bartender_chat",
            re.compile(
                r"bartender.chat|bar.banter|how.s?.*(?:business|the.bar|the.night)|"
                r"(?:busy|slow).*night|chat.with.me|talk.to.me.bartender",
                re.IGNORECASE,
            ),
            pool="_bartender_chat",
        ),
    ),
)
