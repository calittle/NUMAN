# Rob's NUMAN Configuration Guide

This guide explains what can be changed in NUMAN, where to change it, and how
the pieces fit together. It is written for the person operating and tuning the
show, not for a Python developer.

For installation, starting, stopping, updating, and fault-finding, use
[Rob's NUMAN Guide](ROB-GUIDE.md). This document is the deeper reference for
changing the birds' behavior.

## The short version

NUMAN's editable behavior lives in two places:

| Location | What it controls |
| --- | --- |
| `config\numan.toml` | Characters, voices, physical actors, audio routes, wake words, microphone, speech recognition, language model, and show-control connections |
| `data` | Recipes, exact answers, response variations, character audio clips, and drink-presentation cues |

Most changes take effect after NUMAN is restarted. Wake-phrase changes also
need `wake compile` before restart.

Before editing either location:

1. Stop NUMAN with **Ctrl-C**.
2. Make a backup copy of the file you will edit.
3. Use Notepad or another plain-text editor. Do not use Word.
4. Keep the file type unchanged: TOML stays `.toml` and JSON stays `.json`.
5. Validate and test before a show.

Validate the main settings file with:

```powershell
.\.venv\Scripts\numan.exe config validate --live
```

A successful result contains `"valid": true`. The `--live` check also confirms
that selected audio devices, speech tools, and models are available.

JSON data files are checked when NUMAN starts. If one is malformed, startup
will stop with the name of the bad file. Restoring the backup is usually the
fastest recovery.

## How the pieces fit together

A guest's request travels through these parts:

```text
wake phrase -> wake target -> character -> response -> voice -> actor -> audio route -> speaker
                                   |
                                   +-> optional show action -> Light-O-Rama
```

The names have specific meanings:

- A **character** is the personality and knowledge: Captain Grog or Polly.
- A **voice** turns that character's words into audio and shapes the sound.
- An **actor** is a physical performer, such as one particular Squawker.
- An **audio route** identifies the Windows output used by that actor.
- A **wake target** connects a spoken wake phrase to a character and actor.
- A **recipe** is shared cocktail knowledge. It is not character-specific.
- A **response pool** gives one character several prepared replies to the same
  kind of request.
- A **show action** is a safe name such as `storm`; Light-O-Rama owns the actual
  lighting sequence.

This separation is useful. You can move Polly to a different speaker without
changing her personality, or change Captain Grog's voice without changing his
wake phrase.

## Editing rules: TOML and JSON

`config\numan.toml` uses TOML:

```toml
[section.name]
text = "in quotation marks"
number = 120
enabled = true
list = ["one", "two"]
```

Files under `data` use JSON:

```json
{
  "name": "value",
  "choices": ["one", "two"]
}
```

In JSON, every item except the last item in an object or list needs a comma.
JSON does not allow comments. Use straight quotation marks, not curly “smart”
quotes around keys or values.

IDs such as `grog`, `grog-dev`, and `grog-piper-alan-shrill` are internal names.
They must match everywhere they are referenced. Treat them like labels on
cables: changing one label means changing every connection to it.

## Runtime defaults

File: `config\numan.toml`

```toml
[runtime]
default_character = "grog"
default_actor = "grog-dev"
```

These settings choose the character and physical actor when a command does not
name one explicitly. The default actor must represent the default character.
Wake-word requests use their own target instead, so changing these defaults
does not swap the wake phrases.

## Characters

File: `config\numan.toml`

```toml
[characters.grog]
name = "Captain Grog"
system_prompt = "You are Captain Grog ..."
voice_profile = "grog-piper-alan-shrill"
show_actions = ["storm", "lightning"]
```

Each character has:

- `name`: the human-readable name.
- `system_prompt`: personality and rules used for open-ended AI answers.
- `voice_profile`: the ID of a `[voices...]` section.
- `show_actions`: show effects this character is permitted to request.

The prompt affects only answers that reach the language model. Prepared
responses, recipes, and drink-presentation lines are handled before the model
and are not rewritten by the prompt.

Keep the prompt plain and direct. Important safety rules should remain, notably
the instruction not to invent cocktail recipes and to output only speakable
words. The checked-in prompts also ground both characters as sentient macaws
who tend bar at The Kraken's Curse, including their avian bodies and physical
traits. Keep that identity grounding intact when editing personality details.
Test prompt changes with several open questions, not just `Hello`.

### Adding a character

Adding a new `[characters...]` section alone is not enough. The current program
has dispatch policies only for `grog` and `polly`, and each configured character
also needs matching data files and runtime behavior. Adding a third character
is an Andy/developer change. Rob can safely tune the two existing characters.

## Voices

File: `config\numan.toml`

```toml
[voices.grog-local]
provider = "kokoro"
model = "models/tts/kokoro/kokoro-v1.0.onnx"
voices = "models/tts/kokoro/voices-v1.0.bin"
voice = "am_adam"
language = "en-us"
speed = 1.0
sample_rate = 24000
channels = 1
end_silence_ms = 750
```

NUMAN supports the fully local `piper` and `kokoro` providers. Their models are
loaded once when live mode starts and synthesis needs no network connection.
`edge-tts` remains available as an optional compatibility provider.
The checked-in profiles use Piper for both characters to minimize response
latency. Polly's Kokoro profile remains configured as an optional quality-first
choice; select it by changing `characters.polly.voice_profile`.

A Piper profile instead uses `model`, optional `config`, `speaker`,
`length_scale`, `noise_scale`, and `noise_w_scale`. A Kokoro profile uses
`model`, `voices`, `voice`, `language`, and `speed`. Model paths are relative
to the NUMAN project unless absolute.

- `voice` selects an Edge or Kokoro voice within the configured model bundle.
- `rate` changes speaking speed. Valid range: `-50%` through `+100%`.
- `volume` changes source volume. Valid range: `-100%` through `+100%`.
- `pitch` changes source pitch. Valid range: `-100Hz` through `+100Hz`.
- `sample_rate` and `channels` describe generated audio. Leave them at `24000`
  and `1` unless Andy is changing the audio pipeline.

`rate`, `volume`, and `pitch` apply to the optional Edge provider. Local
providers use their numeric controls before the common tiki voice console.

Test a profile with:

```powershell
.\.venv\Scripts\numan.exe ask --character grog --live "Welcome to the bar"
```

Final postprocessed WAVs are cached automatically. Cache entries include the
response text, provider, model identity, synthesis controls, and tiki-console
filter, so changing any voice setting creates a new entry. NUMAN stores the
cache in `%LOCALAPPDATA%\NUMAN\cache\tts` on Windows and
`~/Library/Caches/NUMAN/tts` on macOS.

### Tiki voice console

The nested `[voices.<id>.tiki_console]` section shapes the generated voice:

| Setting | Effect | Accepted range |
| --- | --- | --- |
| `perch_pitch_semitones` | Overall pitch without changing speed | -12 to 12 |
| `barrel_chest_hz` | Center of the low-mid body | 80 to 1,000 Hz |
| `barrel_chest_db` | Amount of low-mid body | -20 to 20 dB |
| `barrel_chest_width` | Breadth of the body band | 0.1 to 10 |
| `beak_bite_hz` | Center of the nasal/beak tone | 100 to 12,000 Hz |
| `beak_bite_db` | Strength of the beak tone | -30 to 30 dB |
| `beak_bite_width` | Focus of the beak tone | 0.1 to 10 |
| `feather_sparkle_hz` | Center of high-frequency brightness | 100 to 12,000 Hz |
| `feather_sparkle_db` | Amount of brightness | -30 to 30 dB |
| `coconut_radio_bits` | Lo-fi texture; lower is crunchier | 2 to 16 |
| `rum_barrel_lufs` | Final loudness; nearer zero is louder | -30 to -5 LUFS |

Change one value at a time and keep notes. Large boosts can make a voice harsh
even when they pass validation.

An advanced voice can use `ffmpeg_filter = "..."` instead of `tiki_console`,
but never both. Raw filters are an Andy/developer setting because a valid TOML
file can still contain an unusable audio filter.

## Audio routes and physical actors

File: `config\numan.toml`

An audio route selects a Windows output:

```toml
[audio_routes.grog-squawker]
backend = "sounddevice"
device = "Windows DirectSound::Speakers (USB Audio Device)"
```

An actor connects a character to that route:

```toml
[actors.grog-dev]
type = "squawker"
character = "grog"
audio_route = "grog-squawker"
```

Available route backends are:

- `system-default`: uses the normal Windows speaker. Its device must also be
  `"system-default"`.
- `sounddevice`: uses one exact output selector, appropriate for dedicated USB
  audio adapters.

List the current selectors with:

```powershell
.\.venv\Scripts\numan.exe devices list
```

Copy the entire `selector` value into `device`. Keep each USB adapter in its
labeled USB port because Windows can rename or reorder devices after moves.

The only supported actor `type` is currently `squawker`. Multiple actors may
represent the same character, but commands then need `--actor` unless one is
the runtime default. A wake target always names one exact actor.

## Microphone and speech recognition

File: `config\numan.toml`

```toml
[microphone]
device = "system-default"
sample_rate = 16000
channels = 1
```

List input selectors with:

```powershell
.\.venv\Scripts\numan.exe devices inputs
```

Use `system-default` or copy the complete selector. NUMAN requires one channel;
leave the sample rate at `16000` unless Andy changes the speech models.
`end_silence_ms` is the quiet period that ends a question; lowering it improves
response time but can clip a speaker who pauses between phrases. The supported
range is 200–2000 ms, with 750 ms as the cross-platform default.
The detector learns a low-biased ambient noise floor continuously before the
wake word and during non-speech frames. Its threshold therefore follows steady
room noise without treating a brief voice or clatter as the new baseline.

The `[stt]` section controls speech-to-text. The normal local setup is:

```toml
[stt]
provider = "whisper-server"
model = "models/ggml-base.en.bin"
command = "whisper-server"
host = "127.0.0.1"
port = 8178
use_gpu = false
language = "en"
prompt = "Captain Grog, Polly, Mai Tai, ..."
```

- `model` is the local Whisper model file.
- `command` is the installed Whisper server executable. NUMAN starts it on
  localhost and keeps the model resident between questions.
- `host` must remain localhost; captured speech is never sent off the machine.
- `use_gpu` enables whisper.cpp acceleration when the installation supports it;
  CPU mode is the cross-platform default.
- `language` is the recognition language.
- `prompt` gives Whisper spellings it should expect. Add unusual drink names,
  character names, or venue terms here, separated by commas.

`deepgram` is also supported, using `endpoint` and the environment-variable
name in `api_key_env`. It sends recorded speech to an online service and is an
Andy/developer setup. Never put the actual API key in `numan.toml`.

Check recognition with:

```powershell
.\.venv\Scripts\numan.exe stt status
.\.venv\Scripts\numan.exe listen --live
```

## Wake words and routing

File: `config\numan.toml`

```toml
[wake]
enabled = true
model_dir = "models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
threshold = 0.20
score = 1.0

[wake.targets.grog]
phrases = ["hey captain grog"]
character = "grog"
actor = "grog-dev"
```

- `enabled` controls whether normal startup uses wake detection.
- `model_dir` points at the installed wake model. Do not move it casually.
- `threshold` controls acceptance. A higher value is stricter and may reduce
  false wakes while also missing quiet or unclear calls. Valid range is above
  zero through 1.
- `score` adjusts keyword weighting and must be positive. Leave it at `1.0`
  unless tuning with Andy.
- Each target has one or more `phrases`, plus the exact character and actor to
  answer.

Phrases must be unique across all targets. After any phrase change, run:

```powershell
.\.venv\Scripts\numan.exe wake compile
.\.venv\Scripts\numan.exe wake listen
```

The first command rebuilds the keyword file. The second lets you test detection
without making a bird answer. Restart NUMAN after a successful test.

## Prepared character responses

Each character has two editable JSON files:

```text
data\grog\exact_cache.json
data\grog\response_pools.json
data\polly\exact_cache.json
data\polly\response_pools.json
```

### Exact answers

`exact_cache.json` maps a likely question to one fixed answer:

```json
{
  "who are you": "I'm Polly, the bright-eyed half of this operation."
}
```

Matching ignores capitalization and punctuation during normal dispatch. It can
also match when the stored phrase contains the request or the request contains
the stored phrase. Keep keys specific enough that they do not accidentally
catch unrelated questions.

Use exact answers for lines that must be consistent, quick, and independent of
the language model.

### Response pools

`response_pools.json` maps a phrase or internal pool name to several possible
answers:

```json
{
  "recommend something tropical": [
    "Try a Jungle Bird!",
    "A Mai Tai would be lovely."
  ]
}
```

Public names—those without a leading underscore—can match a guest's words.
NUMAN chooses one response from the matching list. Similar public phrases may
also match fuzzily, so use natural but distinct keys.

Names beginning with `_`, such as `_greetings` and `_show_storm`, are internal
pools used by built-in routines. You can freely add, remove, or rewrite lines
inside an existing pool. Do not rename or delete an internal pool unless Andy
also changes the routine that uses it.

The phrases that activate greetings, tiki facts, taunts, and semantic show
actions are currently Python rules, not settings in these JSON files. Rob can
change what a matched routine says, but adding a new kind of routine or changing
its trigger language is an Andy/developer change.

## Cocktail recipes

Files:

- `data\krakens_curse\recipes.json`: owner-editable house specifications;
- `data\cocktails\recipes.json`: generic reference specifications.

House specifications are checked first and override a generic drink with the
same normalized name or alias. Put venue recipes in the Kraken's Curse file so
upstream reference-data updates do not overwrite Rob's approved builds.

Recipes are shared by all characters and answered before the language model.
Each recipe has this shape:

```json
{
  "name": "Painkiller",
  "aliases": ["Pain Killer"],
  "source": "Pusser's Rum",
  "ingredients": [
    {"amount": "2", "unit": "oz", "name": "Pusser's rum"},
    {"amount": "4", "unit": "oz", "name": "pineapple juice"}
  ],
  "garnish": "freshly grated nutmeg"
}
```

- `name` is the spoken drink name.
- `aliases` are alternate names or likely transcriptions. They must not
  duplicate another recipe's name or alias after normalization.
- `source` records recipe provenance. It is required even though it is not
  currently spoken.
- `ingredients` must contain at least one item. `amount`, `unit`, and `name`
  are stored as text so fractions and decimals are allowed.
- `garnish` is spoken when present. Use `null` or omit it for no garnish.

Known units `ml`, `oz`, `tsp`, `dash`, and `drop` are expanded naturally when
spoken. Other units are spoken exactly as written. Amount `1` or `1.0` uses the
singular form.

Adding a recipe does not automatically add a theatrical drink presentation.
Those are separate: recipes answer “what is in it?”, while presentation cues
react to ordering or serving selected drinks.

Test a recipe in safe mode:

```powershell
.\.venv\Scripts\numan.exe ask --character grog "What is in a Painkiller?"
```

The result should report `"source": "structured_lookup"` and does not need
`--live`.

The operator's complete phrase matrix in `docs\ROB-GUIDE.md` covers exact
caches, pools, recipes, character routines, presentation cues, semantic show
actions, Ollama fallback, both wake targets, and noisy-room capture. Run that
checklist after changing dispatch data, voice profiles, microphone behavior, or
show-control configuration.

## Kraken's Curse venue lore

File: `data\krakens_curse\lore.json`

Venue history, named objects, recurring stories, house rules, and other stable
facts belong here rather than in the language-model prompt. Each entry has a
unique `id`, unique question `aliases`, provenance in `source`, and concise
spoken `responses` keyed by `grog`, `polly`, or `default`. Lore is matched
before cocktail lookup and Ollama and reports `"source": "venue_lore"`.

Run `numan knowledge status` after every lore or house-recipe edit, then run
`numan voice cache build` so the validated deterministic answers are ready
without synthesis delay. See `docs\ROB-GUIDE.md` for copyable JSON examples and
the operator workflow.

## Drink-presentation cues

File: `data\show\drink_presentations.json`

These records connect an order or serving announcement to a prepared character
line and a delayed or immediate semantic show action:

```json
{
  "jet_pilot": {
    "aliases": ["jet pilot"],
    "show_action": "present_jet_pilot",
    "order_delay_seconds": 120,
    "serving_delay_seconds": 0,
    "cooldown_seconds": 30,
    "responses": {
      "grog": ["A Jet Pilot? Very well."],
      "polly": ["One Jet Pilot! Coming right up."]
    }
  }
}
```

- The outer key (`jet_pilot`) is an internal drink ID.
- `aliases` are phrases NUMAN looks for in the request; at least one is
  required.
- `show_action` must exist in `[show_control].allowed_actions`.
- `order_delay_seconds` is used for requests such as “I want a Jet Pilot.”
- `serving_delay_seconds` is used for “I'm serving a Jet Pilot.”
- `cooldown_seconds` suppresses a duplicate action accepted too soon after the
  previous one.
- `responses` supplies one or more lines per participating character.

Every participating character must exist and must include this show action in
its own `show_actions` list. Delays and cooldowns cannot be negative.

Recipe questions containing words such as “recipe,” “ingredients,” or “what's
in” deliberately do not trigger a presentation. Pending delayed cues exist
only in memory and disappear when NUMAN stops or restarts.

Safe tests:

```powershell
.\.venv\Scripts\numan.exe ask --character grog "I want a Jet Pilot"
.\.venv\Scripts\numan.exe ask --character polly "I'm serving a Jet Pilot"
```

Inspect `show_actions`, `delay_seconds`, and `status` in the output. Without
`--live`, no real Light-O-Rama packet is sent.

## Show control and Light-O-Rama

File: `config\numan.toml`

The safe development setting is:

```toml
[show_control]
provider = "fake"
allowed_actions = ["storm", "lightning", "volcano_rumble", "blackout"]
host = "127.0.0.1"
port = 0
```

Providers are:

- `fake`: accepts and records allowed actions without touching hardware.
- `none`: ignores show actions.
- `lor-osc-trigger`: sends OSC trigger packets to Light-O-Rama in live mode.

`allowed_actions` is the master list. A character's own `show_actions` list is
a second permission boundary. A drink presentation must pass both checks.

For Light-O-Rama, every allowed action needs a trigger mapping:

```toml
[show_control]
provider = "lor-osc-trigger"
allowed_actions = ["storm"]
host = "127.0.0.1"
port = 9000

[show_control.triggers.storm]
network = 0
unit = 1
circuit = 1
```

Valid ranges are network 0–15, unit 1–240, circuit 1–512, and port 1–65535.
The values must match interactive triggers created in the LOR S6 Control Panel.
NUMAN sends only the trigger; LOR owns sequence timing and hardware channels.

Keep `provider = "fake"` until Andy has configured and tested LOR. Review the
mapping without sending a trigger with:

```powershell
.\.venv\Scripts\numan.exe show status
```

## Language model

File: `config\numan.toml`

The normal local setting is:

```toml
[llm]
provider = "ollama"
endpoint = "http://127.0.0.1:11434/api"
model = "llama3.2:3b"
api_key_env = "NUMAN_LLM_API_KEY"
```

Supported providers are:

- `ollama`: local open-ended answers. It requires an endpoint and model.
- `openai-compatible`: an online compatible endpoint, model, and the name of
  an environment variable holding its API key.
- `fake`: a fixed development response; useful for tests, not a show.

`api_key_env` is a variable name, not the secret itself. Never store an API key
in the repository or send it in chat.

Changing the model can change personality, latency, and instruction-following.
The character prompts may need retuning. Check Ollama with:

```powershell
.\.venv\Scripts\numan.exe llm status
```

## Character audio clips

Directories such as `data\grog\audio` and `data\polly\audio` contain cached
acknowledgment clips played while a slower answer is prepared. Their selection
and metadata are currently defined in code. Do not rename, replace, add, or
delete these WAV files as a normal configuration change; ask Andy to rebuild
the character's stalling plan and clips together.

## What is configurable without code

Rob can safely change, with backup and testing:

- the two characters' wording and prompts;
- voice choice, speed, volume, pitch, and tiki-console tone;
- microphone and speaker selectors;
- which existing actor and character answer a wake phrase;
- wake phrases and cautious threshold tuning;
- exact replies and response-pool lines;
- cocktail recipes and aliases;
- existing or new drink-presentation data using existing show actions;
- show-action permissions, delays, cooldowns, and preconfigured LOR mappings;
- the supported speech and language-model provider settings.

Ask Andy for a code change to:

- add a third character;
- add a new actor type other than `squawker`;
- create a new routine or alter the words that activate a routine;
- add a new voice, speech, or show-control provider;
- change conversation-history limits or persistence;
- change how recipes are phrased when spoken;
- change the set or timing of acknowledgment clips;
- make delayed show cues survive a restart.

## Recommended change workflow

1. Do not make configuration changes during a show.
2. Stop NUMAN cleanly.
3. Back up the specific file and note what you intend to change.
4. Make one logical change at a time.
5. For `numan.toml`, run `config validate --live`.
6. For wake phrases, run `wake compile` and `wake listen`.
7. Exercise the change in safe mode without `--live` when possible.
8. Test the intended character with `--live` if audio is involved.
9. Start NUMAN normally and perform one end-to-end wake test.
10. Keep the backup until after the next successful show.

Back up the complete `config` and `data` folders after meaningful changes. They
contain the small, irreplaceable local customization; models and the Python
environment can be downloaded again.

## Quick test checklist

After a significant configuration change, run the applicable commands:

```powershell
.\.venv\Scripts\numan.exe config validate --live
.\.venv\Scripts\numan.exe devices inputs
.\.venv\Scripts\numan.exe devices list
.\.venv\Scripts\numan.exe stt status
.\.venv\Scripts\numan.exe llm status
.\.venv\Scripts\numan.exe wake status
.\.venv\Scripts\numan.exe show status
.\.venv\Scripts\numan.exe ask --character grog "What is in a Mai Tai?"
.\.venv\Scripts\numan.exe ask --character polly --live "Hello"
```

Finish by running `scripts\windows\CHECK-NUMAN.cmd`. Every line should begin
with `[OK]` before the system is considered show-ready.
