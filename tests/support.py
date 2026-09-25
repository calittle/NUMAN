"""Small fixtures shared by character-independent unit tests."""

from numan.characters.dispatch import build_character_dispatcher
from numan.characters.nigel import NIGEL_DISPATCH_POLICY
from numan.engine.models import Character


TEST_NIGEL = Character(
    id="nigel",
    name="Nigel",
    system_prompt="Test prompt.",
    voice_profile="nigel-edge-ryan-shrill",
)


def build_nigel_test_dispatcher(**kwargs):
    return build_character_dispatcher(policy=NIGEL_DISPATCH_POLICY, **kwargs)
