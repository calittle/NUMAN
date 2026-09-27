# Rob's NUMAN Guide

This is the everyday guide for the Windows show computer. You do not need to
understand Python, AI models, or audio programming to operate NUMAN.

Keep drinks away from the laptop. Captain Grog can survive rum. Windows cannot.

## The four things to remember

1. Double-click `CHECK-NUMAN.cmd` when something seems wrong.
2. Double-click `START-NUMAN.cmd` to start the birds.
3. Double-click `UPDATE-NUMAN.cmd` when Andy says an update is ready.
4. Keep the black PowerShell window open while NUMAN is running.

## First-time installation

Andy should be present for this part.

### 1. Install Python

Install **64-bit Python 3.12 or newer** from [python.org](https://www.python.org/downloads/).
On the first installer screen, check **Add Python to PATH**.

NUMAN is tested on Python 3.12 and Python 3.14. Do not install an older version.

### 2. Install Git

Install [Git for Windows](https://git-scm.com/download/win) with its normal
recommended options. Git is what allows `UPDATE-NUMAN.cmd` to download updates
without replacing local configuration or models.

### 3. Put NUMAN in a permanent folder

Use a simple location that will not move, for example:

```text
C:\NUMAN\numan
```

Do not run it from Downloads, OneDrive, or a USB stick.

Andy should install NUMAN with Git rather than downloading a ZIP:

```powershell
git clone https://github.com/calittle/NUMAN.git C:\NUMAN\numan
```

An older installation copied without its hidden `.git` folder cannot use the
updater and should be reinstalled with this command.

### 4. Run the setup script

In File Explorer, open `scripts`, then `windows`, and double-click
`SETUP-NUMAN.cmd`. If Windows shows a warning, choose **Run anyway** only if
the NUMAN folder came directly from Andy.

The script installs NUMAN's private Python environment and downloads the
speech, wake-word, and local-language models. It may take several minutes and
download more than a gigabyte. Existing files are reused if setup is run again.

If Windows asks whether FFmpeg or Ollama may be installed, approve it. If the
script says to restart Windows, restart and run the same setup command again.

Successful setup ends with:

```text
Everything needed for normal operation is ready.
```

## Starting NUMAN

In the `scripts\windows` folder, double-click `START-NUMAN.cmd`.

Leave that window open. When it says it is listening, try:

```text
Hey Captain Grog
Tell me a tiki fact
```

or:

```text
Hey Polly
Are you a good bird?
```

## Stopping NUMAN

Click the NUMAN PowerShell window and press **Ctrl-C once**. Wait for:

```text
Wake listener stopped.
```

Do not simply power off the computer while the program is speaking.

## Checking the system

Run this whenever something is not working:

Double-click `scripts\windows\CHECK-NUMAN.cmd`.

Every line should start with `[OK]`. A `[FIX]` line explains what is missing.
Send Andy a photo or copy of the complete check if the suggested fix does not
work.

## Testing one part at a time

Open a terminal in the NUMAN folder before using these commands.

### Test Captain Grog without the microphone

```powershell
.\.venv\Scripts\numan.exe ask --character grog --live "Hello"
```

### Test Polly without the microphone

```powershell
.\.venv\Scripts\numan.exe ask --character polly --live "Hello"
```

### See microphones

```powershell
.\.venv\Scripts\numan.exe devices inputs
```

### See speakers and Squawker outputs

```powershell
.\.venv\Scripts\numan.exe devices list
```

### Test speech recognition without wake words

```powershell
.\.venv\Scripts\numan.exe listen --live
```

Press Enter to begin recording, speak, and press Enter again.

### Test wake words without making the birds answer

```powershell
.\.venv\Scripts\numan.exe wake listen
```

Say “Hey Captain Grog” and “Hey Polly.” Press Ctrl-C once when finished.

## Configuration

The main settings file is:

```text
config\numan.toml
```

Before editing it, make a copy named `numan.toml.backup`. Use Notepad. Change
only the specific value you intend to change, and do not remove quotation marks
or section headings.

After every edit, run:

```powershell
.\.venv\Scripts\numan.exe config validate --live
```

If it reports `"valid": true`, the file is usable. If not, restore the backup
and ask Andy for help.

### Selecting microphones and speakers

Use `devices inputs` and `devices list` to find the exact selector. Copy the
whole selector, including the part before and after `::`.

The microphone setting is:

```toml
[microphone]
device = "system-default"
```

Each bird has an audio route. During initial setup both can use the normal
Windows speaker. Once dedicated USB audio adapters are connected, Andy will
change each route to `backend = "sounddevice"` and paste its selector into the
`device` line.

Windows may reorder USB audio devices if adapters are moved to different USB
ports. Keep each adapter in its labeled port.

### Adjusting a voice

Voice delivery controls (`rate`, `volume`, and `pitch`) sit directly under each
`[voices...]` heading. Tone controls are under the matching
`[voices....tiki_console]` heading. Make small changes and test one bird. The
comments in the file explain every control. Restore the backup if the result
sounds worse.

### Changing wake phrases

Wake phrases appear under `[wake.targets.grog]` and
`[wake.targets.polly]`. After changing one, run:

```powershell
.\.venv\Scripts\numan.exe wake compile
```

Then restart NUMAN.

## Light-O-Rama

Leave `provider = "fake"` until Light-O-Rama S6, its Advanced license,
interactive groups, and sequences are installed. Fake mode is safe: NUMAN
reports cues but sends nothing to lighting hardware.

Andy will configure the OSC port and trigger mappings when the LOR sequences
exist. Rob should not change network, unit, or circuit numbers casually.

## Common problems

### “Command not found” or “not recognized”

Make sure the terminal is open in the NUMAN folder and that the command starts
with `.\.venv\Scripts\`. If the entire `.venv` folder is missing, rerun setup.

### Captain Grog or Polly does not hear the wake phrase

1. Double-click `CHECK-NUMAN.cmd`.
2. Confirm the intended microphone is connected.
3. Run `devices inputs` and check the configured microphone.
4. Run `wake listen` and test in a quiet room.

### The bird hears words but does not speak

1. Confirm the Squawker audio cable and power.
2. Test the character directly with `numan.exe ask ... --live`.
3. Run `devices list` and check the configured output.
4. Check the Windows volume mixer and make sure PowerShell/Python is not muted.

### Answers work but open questions fail

Ollama may not be running. Start Ollama from the Windows Start menu, then run:

```powershell
ollama pull llama3.2:3b
.\.venv\Scripts\numan.exe llm status
```

### A two-minute drink cue disappeared

Pending cues live only while NUMAN is running. If NUMAN was stopped or the
computer restarted, ask for the drink again. This is expected behavior.

### Configuration is broken

Replace `config\numan.toml` with `config\numan.toml.backup`, then validate it.
Do not keep guessing at punctuation in the TOML file.

## Updating NUMAN

Only update when Andy says a new version is ready. Do not update during a show
or immediately before opening the bar.

### Normal update

1. Stop NUMAN with **Ctrl-C** and wait for `Wake listener stopped.`
2. Make sure the computer is connected to the internet.
3. In File Explorer, open the NUMAN folder, then `scripts`, then `windows`.
4. Double-click `UPDATE-NUMAN.cmd`.
5. Leave the black window open while it downloads and checks the update. This
   can take several minutes.
6. Wait for the green message:

```text
NUMAN is up to date and ready.
```

7. Press any key to close the updater. NUMAN can now be started normally with
   `START-NUMAN.cmd`.

The updater keeps downloaded models and local configuration, refreshes NUMAN's
private Python environment, rebuilds wake phrases, validates the configuration,
and runs the normal readiness check. A warning about local changes is expected
when this installation has customized microphone, speaker, or show settings.

### If the update stops with an error

The updater never resets, hides, or discards local files. If a local change
overlaps an incoming update, Git stops instead of guessing. The currently
installed NUMAN files remain on the computer.

Do not delete files, reinstall Git, or run commands copied from the internet.
Take a photo of the complete black window, including the first red error, and
send it to Andy. Leave the window open until the error has been recorded.

If the download worked but the final readiness check shows a `[FIX]` line, the
update itself succeeded. Follow that line or send Andy a photo before starting
the birds.

## What to back up

Back up these small folders after meaningful changes:

```text
config
data
```

The `.venv`, `models`, and `tools\whisper` folders are large but replaceable;
the setup script can recreate them.
