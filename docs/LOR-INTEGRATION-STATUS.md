# LOR integration inspection - 2026-09-27

Inspected the running Control Panel in the NumanShow account without changing
LOR settings or sending commands to its show player.

## Observed installation

- Control Panel window title: Light-O-Rama Control Panel v6.6.12 Basic.
- Executable product/file version: 6.6.0.12.
- Account data folder: `C:\Users\NumanShow\Documents\Light-O-Rama`.
- `CommonData/TraySettings.json`: OSC disabled; configured UDP port 8000;
  selected address is a LAN interface, not loopback. NUMAN's localhost default
  must be reconciled with the LOR listening interface before testing.
- TriggerOptions and LiveCueList are empty; LastPlayerMode is unset.
- `CommonData/ShowScheduleSettings.json`: Shows is empty.
- Sequences directory contains only the five bundled sample .loredit files.
  No user show or interactive-group mapping was found in this account's data.
- Startup trace reports zero LOR networks and zero DMX networks.
  The listener on 127.0.0.1:8837 is LOR's communications listener, not OSC.

These are account-specific findings, not proof that another Windows account
has no existing show data. Live playback status was not visually verified:
window capture timed out and UI navigation failed with "coordinate input
geometry is unavailable". No play, stop, lighting-test, or configuration
controls were successfully operated.

## Licensing blocker

The current official feature table lists REST API and OSC (S6.2.4+) under Pro.
Advanced supports interactive shows but does not provide this OSC interface.
The running Basic installation cannot complete the requested OSC acceptance
test. Cal needs to confirm an existing Pro entitlement or decide whether to
obtain one; no purchase or activation was attempted.

Source: https://store.lightorama.com/pages/software-license-features
Protocol: https://www1.lightorama.com/help/osc-messages.htm

## Validation and next step

All four tests in tests/test_lor_osc.py pass. An isolated ephemeral UDP socket
on loopback received the exact expected /trigger packet from a preview_test
semantic action using the real OSCUDPTransport. That test did not address LOR
or hardware and does not demonstrate LOR reception or sequence execution.

After Pro is available, verify the active player state, preserve the account's
show data, and create a dedicated software-only preview sequence and trigger.
Keep physical outputs unassigned. Match the OSC listener address/port in an
isolated NUMAN test configuration, then verify both LOR's receipt and visible
preview playback. Do not reuse an existing effect mapping without inspecting it.

The production configuration remains provider = "fake", port = 0, with no
active trigger mappings. No LOR configuration was changed, so no runtime
rollback is needed.
