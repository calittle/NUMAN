"""Audio endpoint discovery without importing optional dependencies eagerly."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioDevice:
    device_index: int | None
    selector: str
    name: str
    host_api: str
    output_channels: int
    input_channels: int = 0
    is_default: bool = False


def list_audio_outputs() -> tuple[AudioDevice, ...]:
    """Return the OS-default fallback plus any addressable outputs."""
    fallback = AudioDevice(
        None, "system-default", "System default", "operating-system", 2,
        is_default=True,
    )
    try:
        import sounddevice as sd
    except ImportError:
        return (fallback,)

    host_apis = sd.query_hostapis()
    default_output = sd.default.device[1]
    outputs = []
    for index, raw in enumerate(sd.query_devices()):
        channels = int(raw["max_output_channels"])
        if channels <= 0:
            continue
        host_index = int(raw["hostapi"])
        host_name = str(host_apis[host_index]["name"])
        # Host API + exact device name is more resilient than the volatile
        # numeric index; the backend resolves it afresh at startup.
        selector = f"{host_name}::{raw['name']}"
        outputs.append(
            AudioDevice(
                device_index=index,
                selector=selector,
                name=str(raw["name"]),
                host_api=host_name,
                output_channels=channels,
                input_channels=int(raw["max_input_channels"]),
                is_default=index == default_output,
            )
        )
    return (fallback, *outputs)


def list_audio_inputs() -> tuple[AudioDevice, ...]:
    fallback = AudioDevice(
        None, "system-default", "System default", "operating-system", 0,
        input_channels=1, is_default=True,
    )
    try:
        import sounddevice as sd
    except ImportError:
        return (fallback,)
    host_apis = sd.query_hostapis()
    default_input = sd.default.device[0]
    inputs = []
    for index, raw in enumerate(sd.query_devices()):
        channels = int(raw["max_input_channels"])
        if channels <= 0:
            continue
        host_name = str(host_apis[int(raw["hostapi"])]["name"])
        inputs.append(AudioDevice(
            index,
            f"{host_name}::{raw['name']}",
            str(raw["name"]),
            host_name,
            int(raw["max_output_channels"]),
            input_channels=channels,
            is_default=index == default_input,
        ))
    return (fallback, *inputs)


def resolve_input_device(selector: str) -> int | None:
    matches = [device for device in list_audio_inputs() if device.selector == selector]
    if not matches:
        raise LookupError(f"configured microphone is unavailable: {selector}")
    return matches[0].device_index


def resolve_audio_device(selector: str) -> int:
    matches = [device for device in list_audio_outputs() if device.selector == selector]
    if not matches:
        raise LookupError(f"configured audio device is unavailable: {selector}")
    if matches[0].device_index is None:
        raise LookupError(f"configured route is not device-addressable: {selector}")
    return matches[0].device_index
