from __future__ import annotations

from .models import CeilingFanError, DeviceProfile, LearnedWaveform, ProtocolSpec


INSPIRE_PRO_COMMANDS = {
    "fan_off": 0xE2,
    "fan_speed_1": 0xF5,
    "fan_speed_2": 0xED,
    "fan_speed_3": 0xE5,
    "fan_speed_4": 0xDD,
    "fan_speed_5": 0xD5,
    "fan_speed_6": 0xCD,
    "light_off": 0xDB,
    "light_brightness_1": 0xFC,
    "light_brightness_2": 0xF4,
    "light_brightness_3": 0xEC,
    "light_brightness_4": 0xE4,
    "light_brightness_5": 0xDC,
    "light_brightness_6": 0xD4,
    "light_brightness_7": 0xCC,
    "light_brightness_8": 0xC4,
}

CJOY_COMMANDS = {
    "fan_off": 0x1F,
    "fan_speed_1": 0x2B,
    "fan_speed_2": 0x10,
    "fan_speed_3": 0x08,
    "fan_speed_4": 0x2F,
    "fan_speed_5": 0x23,
    "fan_speed_6": 0x04,
    "light_toggle": 0x20,
    "dimmer_down": 0x19,
    "dimmer_up": 0x21,
}

CJOY_PHASE_FOLDS = (0xCE, 0x0D, 0x95, 0x67)
CJOY_WAKE = (8805, 2860)
CJOY_HEADER = (7394, 1083)
CJOY_ZERO = (348, 721)
CJOY_ONE = (742, 329)
CJOY_REPETITIONS = 5


def cjoy_tail(command: int, phase: int) -> int:
    """Return the captured 11-bit CJOY phase/checksum suffix."""
    if not 0 <= command < (1 << 6):
        raise CeilingFanError("CJOY command must be a 6-bit value")
    if not 0 <= phase < 4:
        raise CeilingFanError("CJOY phase must be between 0 and 3")
    high = 1 if phase < 2 else 0
    phase_code = (high << 8) | (
        (((command << 1) | high) ^ CJOY_PHASE_FOLDS[phase]) & 0xFF
    )
    return (phase_code << 2) | 0b10


def cjoy_waveform(remote_id: int, command: int, phase: int) -> list[int]:
    if not 0 <= remote_id < (1 << 32):
        raise CeilingFanError("CJOY remote ID must be a 32-bit value")
    frame = (remote_id << 17) | (command << 11) | cjoy_tail(command, phase)
    waveform = [CJOY_WAKE[0], -CJOY_WAKE[1]]
    for _ in range(CJOY_REPETITIONS):
        waveform.extend((CJOY_HEADER[0], -CJOY_HEADER[1]))
        for bit in range(48, -1, -1):
            mark, space = CJOY_ONE if frame & (1 << bit) else CJOY_ZERO
            waveform.extend((mark, -space))
    return waveform


def _inspire_pro_waveform(command: int, remote_id: int) -> LearnedWaveform:
    bits = [bool(command & (1 << bit)) for bit in range(7, -1, -1)]
    bits.extend(bool(remote_id & (1 << bit)) for bit in range(24, -1, -1))
    frame: list[int] = []
    for index, bit in enumerate(bits):
        frame.append(355 if bit else 1053)
        next_bit = bits[index + 1] if index + 1 < len(bits) else False
        frame.append(-(1031 if next_bit else 337))
    return LearnedWaveform(
        preamble_us=[1053],
        frame_us=frame,
        gap_us=7688,
        repetitions=7,
        trailing_space_us=337,
        confidence=1.0,
        observations=0,
    )


def build_inspire_pro_profile(name: str, remote_id: int) -> DeviceProfile:
    if not 0 <= remote_id < (1 << 25):
        raise CeilingFanError("Inspire Pro remote ID must be a 25-bit value")
    commands = {
        label: _inspire_pro_waveform(command, remote_id)
        for label, command in INSPIRE_PRO_COMMANDS.items()
    }
    return DeviceProfile(
        name=name,
        frequency_hz=433_920_000,
        commands=commands,
        notes=[
            "Generated from the verified Inspire Pro protocol adapter.",
            f"Remote identity: 0x{remote_id:07X} (25 bits).",
        ],
    )


def build_cjoy_profile(name: str, remote_id: int) -> DeviceProfile:
    if not 0 <= remote_id < (1 << 32):
        raise CeilingFanError("CJOY remote ID must be a 32-bit value")
    return DeviceProfile(
        name=name,
        frequency_hz=433_920_000,
        protocol=ProtocolSpec(
            family="cjoy",
            remote_id=remote_id,
            commands=dict(CJOY_COMMANDS),
        ),
        schema_version=2,
        notes=[
            "Generated from the captured CJOY four-phase protocol adapter.",
            f"Remote identity: 0x{remote_id:08X} (32 bits).",
            "Receiver replay and phase enforcement still require physical validation.",
        ],
    )
