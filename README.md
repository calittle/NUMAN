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

## Windows show-computer setup

The supported production target is 64-bit Windows with Python 3.12. For the
nontechnical installation, daily-operation, configuration, backup, and
troubleshooting instructions, use [Rob's NUMAN Guide](docs/ROB-GUIDE.md).
The one-time installer and double-clickable start/check launchers are in
`scripts/windows`. Run `numan doctor` at any time for a plain-language
readiness report.

## Platform support

NUMAN keeps its configuration, show logic, speech pipeline, and tests
operating-system neutral. Playback uses Windows PowerShell, macOS `afplay`, or
Linux PulseAudio; dedicated device routing uses `sounddevice` on all three.
The production installer above is Windows-specific because that is the show
computer Rob will operate. Development is exercised on macOS. Linux is
supported by the code but has not yet had a full hardware dress rehearsal.

On macOS or Linux, install Python 3.12 or newer plus FFmpeg, then run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,live,api,wake]"
.venv/bin/numan doctor
```

The local speech and wake model paths are the same on every platform. Follow
the model references in the voice-input and wake-word sections below. Ollama
is optional only when another configured LLM provider is used; the checked-in
configuration expects it.

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

The API exposes `/health`, `/characters`, `/actors`, `/audio/devices`, `/show`,
and `POST /ask`. Conversation history is isolated by character and conversation
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

## Semantic show control

NUMAN can request named environmental effects without containing their
choreography. The initial hardware-safe provider records `storm`, `lightning`,
`volcano_rumble`, and `blackout`; it never talks to real lighting hardware.
Character allowlists provide a second authorization boundary: Nigel may
request all four actions, while Polly currently has only storm and lightning.

```bash
numan show status
numan ask --character nigel "Bring on a storm"
numan ask --character polly "Give me lightning"
```

The CLI/API result reports `show_actions`, and `GET /show` reports provider and
permission diagnostics. A future Light-O-Rama transport will map each semantic
name to a designer-authored sequence; NUMAN will not own channel-level timing.

### Drink presentation cues

Curated drink cues live in `data/show/drink_presentations.json`. Each record
defines aliases, character-specific responses, a semantic action, duplicate
cooldown, and separate delays for an order versus a bartender's serving
announcement. For example, Jet Pilot and Suffering Bastard orders currently
schedule their presentation two minutes after the bird finishes speaking;
"I'm serving ..." fires the presentation immediately after speech playback.

```text
"I want a Jet Pilot"                 -> delay 120 seconds
"I'm serving a Suffering Bastard"    -> delay 0 seconds
"What's in a Jet Pilot?"             -> no presentation cue
```

Delayed actions are non-blocking. Inspect them with `GET /show/cues` and cancel
one with `DELETE /show/cues/{id}`. The initial scheduler is in memory, so use
the persistent API or wake runtime for delayed cues; exiting or restarting the
process intentionally discards pending work. Persistence can be added later if
show cues must survive a restart.

### Light-O-Rama Advanced integration

The production adapter targets the OSC interactive-trigger feature available
with an Advanced or Pro LOR license. It sends LOR's documented
`/trigger network unit circuit` message over UDP, normally to the S6 Control
Panel on the same Windows computer. LOR owns the interactive group and every
sequence within it; NUMAN only maps a semantic action to its virtual trigger.

Keep `provider = "fake"` until S6 is installed. Then enable OSC reception in
the Control Panel, choose its UDP port, configure an interactive trigger for
each sequence, and change the provider:

```toml
[show_control]
provider = "lor-osc-trigger"
host = "127.0.0.1"
port = 9000 # Use the actual port selected in LOR.

[show_control.triggers.storm]
network = 0
unit = 1
circuit = 1

[show_control.triggers.present_jet_pilot]
network = 0
unit = 1
circuit = 2
```

Every allowed action must have a mapping, and network (0–15), unit (1–240),
and circuit (1–512) ranges are validated at startup. `numan show status`
prints the complete destination and mapping without sending anything. Normal
safe mode always substitutes the fake recorder; only `--live` or a live API
runtime enables UDP transmission. OSC uses UDP and does not acknowledge cue
execution, so operational confirmation will ultimately come from LOR's player
log or a separate health/telemetry mechanism.

References: [LOR OSC messages](https://www1.lightorama.com/downloads/6.3.2/help/osc-messages.htm)
and [LOR license feature comparison](https://www1.lightorama.com/help/feature_comparison.htm).

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
