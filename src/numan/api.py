"""FastAPI runtime over the NUMAN application services."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from pydantic import BaseModel

from .application import PROJECT_ROOT, Application, build_application
from .configuration import load_config
from .devices import list_audio_outputs
from .engine.models import Utterance


class AskRequest(BaseModel):
    question: str
    character_id: str | None = None
    actor_id: str | None = None
    conversation_id: str = "api"


def create_app(
    config_path: str | Path = PROJECT_ROOT / "config/numan.toml",
    *,
    live: bool = False,
    application: Application | None = None,
):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("install NUMAN with [api] to run the API") from exc

    runtime = application or build_application(load_config(config_path), live=live)
    app = FastAPI(title="NUMAN", version="0.1.0")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "live": live,
            "audio_backend": "real" if live else "fake",
        }

    @app.get("/characters")
    async def characters():
        return [
            {"id": item.id, "name": item.name, "voice_profile": item.voice_profile}
            for item in runtime.characters.values()
        ]

    @app.get("/actors")
    async def actors():
        return [
            {
                "id": item.id,
                "type": item.type,
                "character": item.character,
                "audio_route": item.audio_route,
            }
            for item in runtime.config.actors.values()
        ]

    @app.get("/audio/devices")
    async def audio_devices():
        return [asdict(item) for item in list_audio_outputs()]

    @app.post("/ask")
    async def ask(request: AskRequest):
        question = request.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="question must not be empty")
        character_id = request.character_id or runtime.config.default_character
        actor_id = request.actor_id or runtime.config.default_actor
        character = runtime.characters.get(character_id)
        if character is None:
            raise HTTPException(status_code=404, detail=f"unknown character: {character_id}")
        try:
            result = await runtime.orchestrator.perform(
                Utterance(question, character_id, request.conversation_id),
                character,
                actor_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "character_id": character_id,
            "actor_id": result.actor_id,
            "conversation_id": request.conversation_id,
            "source": result.plan.source.value,
            "response": result.plan.text,
            "route_id": result.route_id,
            "played": result.played,
            "stall_played": result.stall_played,
            "timings": asdict(result.timings),
            "dispatch": [asdict(item) for item in result.dispatch_trace.attempts],
        }

    return app
