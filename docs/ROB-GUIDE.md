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

Setup is safe to rerun after a failed download. It retries each large download
three times, skips applications Winget has already installed, and does not
treat "already installed; no upgrade available" as an error. Incomplete model
downloads are kept separate and never mistaken for finished models.

The whisper.cpp project sometimes publishes a stable release without Windows
binaries. Setup automatically selects the newest official release or nightly
build that includes its normal 64-bit Windows package.

The wake-word model is unpacked by Python itself. NUMAN does not depend on the
optional `bzip2` program that some versions of Windows `tar.exe` expect.

The wake-word libraries also need Microsoft's Visual C++ v14 Redistributable.
Setup checks for this runtime and installs the version matching NUMAN's Python
if it is missing. You do not need Visual Studio or any developer tools.

If setup reports `DLL load failed while importing _sentencepiece`, use the
latest NUMAN setup script and rerun `SETUP-NUMAN.cmd`. It installs the missing
runtime and reuses the downloaded models. If the runtime is already installed
but the error persists, repair it using the
[official Microsoft installer](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist),
restart Windows, and rerun setup.

If Windows asks whether FFmpeg, Ollama, or the Visual C++ runtime may be
installed, approve it. If the
script says to restart Windows, restart and run the same setup command again.

Successful setup ends with:

```text
Everything needed for normal operation is ready.
```

## Unattended startup with a dedicated account

Use this optional setup for a dedicated show computer. Windows automatically
signs into the standard `NumanShow` account; Task Scheduler starts NUMAN and
Ollama in that account's audio session. This is automatic login, not a Windows
service. The show computer must remain powered on and connected to the internet
for Edge TTS.

1. Run `SETUP-NUMAN.cmd` in the installation account (`calit` on this computer).
   After the normal readiness checks pass, answer **Y** to the unattended-startup
   question. If normal setup is already complete, run `ENABLE-UNATTENDED.cmd`
   instead; it performs the same complete startup setup.
2. Setup prepares the shared Python, packages, Ollama, model files, and FFmpeg in
   `C:\ProgramData\NUMAN`. It downloads Microsoft Autologon and verifies its
   Microsoft signature. No manual download or runtime-copy commands are needed.
   It does not copy personal Ollama keys. Stop an existing unattended instance
   before rerunning setup so its runtime can be refreshed safely.
3. Approve the administrator prompt. For a new `NumanShow` account, choose a
   password in the local credential dialog. Setup creates a standard user with
   a nonexpiring password, registers `NUMAN-Show`, and disables plugged-in sleep.
   If Light-O-Rama is installed, it also registers `NUMAN-Light-O-Rama`.
4. If automatic login is not already configured, Microsoft Autologon opens.
   Enter **NumanShow**, this computer's name in **Domain**, and the password from
   step 3, then click **Enable**. Use the password, not a Windows Hello PIN.
   Existing automatic-login credentials are preserved on repeat setup.
   Enter credentials locally, never in chat or a script. Autologon stores a
   Windows LSA secret; administrators can retrieve it.
5. Stop the foreground NUMAN session, then sign into `NumanShow` once. Finish
   Windows first-login screens. Check microphone permission, microphone/speaker
   selection, and Light-O-Rama licensing and show folders in this account.
   NUMAN's triggers remain fake until OSC and mappings are configured.
6. Restart at a convenient time and verify that Windows signs in automatically
   and both birds answer. Setup never signs out or reboots the computer for you;
   this live test confirms the complete startup path.

For scripted installation, pass `-ConfigureUnattended` to `setup.ps1`; plain
`setup.ps1` remains noninteractive unless `-Interactive` is supplied. The account
password and Autologon steps still require local interaction. To omit LOR when
using the standalone startup setup, run `ENABLE-UNATTENDED.cmd -SkipLightORama`.
Run it again after installing LOR to add its startup task.

### Where to find the startup tasks

These are **Scheduled Tasks**, not entries in Windows Services. From `calit`,
open **Task Scheduler as administrator**. Click the **Task Scheduler Library
text** directly beneath **Task Scheduler (Local)** in the left pane. Clicking
only the expand arrow or the top-level summary does not show the task list.
The center pane lists **NUMAN-Show** and, when installed, **NUMAN-Light-O-Rama**.
Press **F5** to refresh. They are in the root library, not under Microsoft.

You can inspect tasks from the administrator account, but they run only in
`NumanShow`'s interactive session. Before that account signs in, **Ready** is
normal. After the 30-second startup delay, expect **Running** for NUMAN. If
necessary, check the task's **Last Run Result** and the log files below.

The tasks wait 30 seconds after sign-in. NUMAN's supervisor waits for Ollama,
restarts NUMAN 15 seconds after an exit, and logs to `C:\ProgramData\NUMAN\logs`.
Task Scheduler restarts a failed supervisor after one minute. Light-O-Rama opens
its Control Panel separately; no shows or hardware triggers are enabled by setup.
Do not also enable Light-O-Rama's own **Launch at Startup** checkbox when using
its scheduled task.

In the show account, use `START-UNATTENDED.cmd`, `STOP-UNATTENDED.cmd`, and
`CHECK-UNATTENDED.cmd` in `scripts\windows`. Do not run `START-NUMAN.cmd` alongside
the task, or two listeners may compete for the microphone. Check `supervisor.log`
and the newest `numan-*.log` when troubleshooting. Logs contain recognized
questions and responses; review and clear old logs as needed.

After updating dependencies, stop the task and rerun `prepare-unattended.ps1`
from the installation account to refresh the shared environment. It refuses to
refresh while its Python or Ollama processes are active. If an Ollama process
remains after stopping, close that process before refreshing. Source/configuration
changes in this checkout are shared immediately; restart the task to load them.

To undo unattended startup, disable the two `NUMAN-*` tasks in Task Scheduler and
click **Disable** in Microsoft Autologon. Restore plugged-in sleep in Windows
power settings if desired. Disabling tasks does not stop a currently running
instance; use `STOP-UNATTENDED.cmd` as well.

## Starting NUMAN

For a foreground installation, double-click `START-NUMAN.cmd` in
`scripts\windows`. For unattended installations, use the startup tasks and
`START-UNATTENDED.cmd` described above instead.

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

The wake phrase alone does not produce a spoken reply. After the `WAKE` line,
say your question within five seconds, then pause. After about a second of
silence, the bird plays a short acknowledgment while preparing the answer. A
`Heard (grog): ...` or `Heard (polly): ...` line confirms that the question was
captured and transcribed. If only `WAKE` appears, check microphone input volume
and move closer: wake detection and question capture use different checks, so
a quiet microphone can detect the wake phrase but miss the question.

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
