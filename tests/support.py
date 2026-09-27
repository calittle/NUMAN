"""Small fixtures shared by character-independent unit tests."""

from numan.characters.dispatch import build_character_dispatcher
from numan.characters.grog import GROG_DISPATCH_POLICY
from numan.engine.models import Character


TEST_GROG = Character(
    id="grog",
    name="Captain Grog",
    system_prompt="Test prompt.",
    voice_profile="grog-edge-ryan-shrill",
)


def build_grog_test_dispatcher(**kwargs):
    return build_character_dispatcher(policy=GROG_DISPATCH_POLICY, **kwargs)
