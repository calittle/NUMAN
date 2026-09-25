# NUMAN

NUMAN is an evolving multi-character AI show-control engine based on the
proven interaction patterns in Nigel.

The current implementation is a platform-neutral, typed, fast-first dispatcher.
It includes Nigel-compatible normalization and routine precedence, JSON-backed
exact caches and response pools, structured-data and LLM provider boundaries,
and rule-level timing diagnostics. It has no audio, hardware, network, or
operating-system dependencies in its core.

The first actor slice adds a Squawker actor, Edge TTS/ffmpeg voice adapter,
per-output serialized playback, and orchestration timings. The CLI is safe by
default: it uses fake synthesis and a null audio backend.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Run a hardware-safe interaction:

```bash
PYTHONPATH=src .venv/bin/python -m numan ask --character nigel "Hello"
```

After installing the project, `PYTHONPATH` is unnecessary:

```bash
.venv/bin/python -m pip install -e ".[dev]"
numan config validate
numan devices list
numan llm status
numan ask "What's in a Mai Tai?"
```

Real synthesis and playback are explicitly opt-in:

```bash
.venv/bin/python -m pip install -e ".[dev,live]"
numan config validate --live
numan ask --live "Hello"
```

Live validation must pass before playback. The checked-in route uses the
operating-system default output for initial bring-up. A physical Squawker
should use a `sounddevice` route selected from `numan devices list`.

Run the persistent safe-mode API:

```bash
.venv/bin/python -m pip install -e ".[dev,live,api]"
.venv/bin/uvicorn numan.server:app --host 127.0.0.1 --port 8765
```

For real synthesis and speaker playback, opt into live mode explicitly:

```bash
NUMAN_LIVE=1 .venv/bin/uvicorn numan.server:app --host 127.0.0.1 --port 8765
```

Check `/health`: `"audio_backend":"real"` confirms audible playback; `"fake"`
means the hardware-safe backend is active.

The API exposes `/health`, `/characters`, `/actors`, `/audio/devices`, and
`POST /ask`. Conversation history is isolated by character and conversation
ID. The checked-in LLM provider is local Ollama using `llama3.2:3b`. Install
Ollama, start its service, and pull that model before asking questions which
fall through the fast routine/cache layers:

```bash
ollama serve
ollama pull llama3.2:3b
numan llm status
```

## Characters and actors

The checked-in development installation has two independently routed
characters: Nigel (`nigel-dev`) and Polly (`polly-dev`). They have distinct
prompts, voice profiles, response caches, pools, wake targets, conversation
history, and logical audio routes. Both development routes currently use the
system-default device; assign each route a `sounddevice` selector when the
physical birds have separate outputs.

Selecting a character automatically selects its sole configured actor:

```bash
numan ask --character polly "Who are you?"
numan ask --character polly --live "Hello"
```

If a character later has multiple physical actors, `--actor` becomes required.
Cocktail recipes are intentionally shared structured knowledge, while each
character owns how it responds through its prompt and character data.

### Tiki voice console

Each configured voice can use a commented `[voices.<id>.tiki_console]` table
instead of maintaining a raw ffmpeg expression. Its controls include perch
pitch, beak bite, feather sparkle, coconut-radio crunch, and rum-barrel
loudness. The checked-in values reproduce the current Nigel and Polly sounds;
edit a value and use `numan ask --character <id> --live "Hello"` to audition
it. Configuration validation rejects unsafe ranges. Advanced profiles may omit
`tiki_console` and provide `ffmpeg_filter` directly as an escape hatch, but a
profile cannot use both.

The `fake` and `openai-compatible` providers remain available for tests and
alternate deployments.

When dispatch reaches the Ollama fallback, NUMAN immediately chooses one of
eight pre-rendered Nigel openers while model inference and answer synthesis run
concurrently. It avoids playing the same opener twice in a row within a running
process. Routine, exact-cache, pool, and structured responses do not stall. CLI
and API results expose `stall_played` for diagnosis.

## Voice input

NUMAN uses local whisper.cpp speech recognition by default, with Deepgram
retained as an optional provider. The checked-in configuration expects the
English base model at `models/ggml-base.en.bin` (models are intentionally not
committed). Inspect and test the input pipeline independently:

```bash
numan devices inputs
numan stt status
numan transcribe path/to/recording.wav
```

Use interactive push-to-talk, transcribe locally, and send the result through
Nigel's normal response pipeline. Press Enter once to start and again to stop:

```bash
numan listen --live
```

For automation, `numan listen --seconds 6 --live` retains fixed-window capture.

Local transcription deliberately runs on CPU so it does not contend with
Ollama for Metal memory. Set `[stt].provider = "deepgram"` to use the optional
prerecorded-audio adapter with `DEEPGRAM_API_KEY`.

## Wake words

Wake phrases are configured per target and compiled for sherpa-onnx at runtime:

```toml
[wake.targets.nigel]
phrases = ["hey nigel"]
character = "nigel"
actor = "nigel-dev"

[wake.targets.polly]
phrases = ["hey polly"]
character = "polly"
actor = "polly-dev"
```

Additional targets use the same single microphone stream. Duplicate phrases,
unknown characters or actors, and character/actor mismatches fail validation.
Inspect, compile, and test routing with:

```bash
numan wake status
numan wake compile
numan wake listen
```

`wake listen` is a detector diagnostic: it only prints the routed target.
Run the complete hands-free pipeline with:

```bash
numan wake run --live
```

Say a configured wake phrase, pause briefly, and ask the question. NUMAN uses
the same continuously open microphone stream for detection and query capture,
ends capture after speech followed by silence, routes the request to the
target's character and actor, and discards microphone input while the answer
is generated and played so the actor cannot wake itself.

## Cocktail knowledge

Recipe questions pass through a local structured catalog before Ollama. The
initial catalog contains sourced specifications for Mai Tai, Jungle Bird,
Zombie, Planter's Punch, and Painkiller. Unknown drinks remain clean provider
misses; Nigel's prompt forbids inventing a recipe on the fallback path.

Records live in `data/cocktails/recipes.json`, while spoken formatting and
alias resolution live in `numan.recipes`. The initial specifications use the
International Bartenders Association list and Pusser's published Painkiller
formula. This provider can later be replaced or augmented by Kapu Tracker
without changing dispatch or orchestration.

The Nigel snapshot in `../nigel` is a behavioral reference. NUMAN code lives
only in this repository.
