"""ASGI import target. Safe mode is the default; NUMAN_LIVE opts into hardware."""

import os

from .api import create_app


def live_from_environment() -> bool:
    value = os.environ.get("NUMAN_LIVE", "").strip().casefold()
    return value in {"1", "true", "yes", "on"}


app = create_app(live=live_from_environment())
