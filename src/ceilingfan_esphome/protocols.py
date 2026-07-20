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


# --- Somfy RTS (motorized blinds, roller shutters, awnings) -----------------
# A public, reverse-engineered rolling-code protocol (Pushstack; Nickduino's
# Somfy_Remote). Like CJOY it is a Dynamic Command family: it is *generated*
# from a persistent per-installation counter, never learned-and-replayed, so a
# capture cannot drive the receiver. Emulating a fresh remote (a chosen 24-bit
# address plus our own rolling code) and pairing it with the motor's PROG button
# is the reliable path. Somfy transmits at 433.42 MHz, not the fan band.
SOMFY_FREQUENCY_HZ = 433_420_000
SOMFY_KEY = 0xA7  # frame[0]; the low nibble is a seed, 0xA7 is conventional.
SOMFY_SYMBOL_US = 640
SOMFY_WAKEUP_US = (9415, 89565)  # first frame only: mark, then space.
SOMFY_HW_SYNC_US = 4 * SOMFY_SYMBOL_US  # 2560; one hardware-sync half-period.
SOMFY_SW_SYNC_US = (4550, SOMFY_SYMBOL_US)  # software sync: mark, then space.
SOMFY_INTERFRAME_US = 30415  # trailing silence after every frame.
SOMFY_FIRST_HW_SYNC = 2  # hardware-sync pulses on the first frame,
SOMFY_REPEAT_HW_SYNC = 7  # and on each repeated frame.
SOMFY_REPEAT_FRAMES = 2  # frames sent after the first (Nickduino default).

# Command nibbles stored in frame[1]'s high nibble. "my" is Somfy's favourite
# position button, universally used as stop.
SOMFY_COMMANDS = {
    "cover_my": 0x1,
    "cover_up": 0x2,
    "cover_down": 0x4,
    "cover_prog": 0x8,
}


def somfy_frame_bytes(remote_id: int, command: int, rolling_code: int) -> list[int]:
    """Return the 7 obfuscated Somfy RTS frame bytes for one button event."""
    if not 0 <= remote_id < (1 << 24):
        raise CeilingFanError("Somfy remote address must be a 24-bit value")
    if command not in set(SOMFY_COMMANDS.values()):
        raise CeilingFanError("Unknown Somfy command nibble")
    if not 0 <= rolling_code < (1 << 16):
        raise CeilingFanError("Somfy rolling code must be a 16-bit value")
    frame = [
        SOMFY_KEY,
        (command & 0x0F) << 4,  # low nibble holds the checksum, added below.
        (rolling_code >> 8) & 0xFF,
        rolling_code & 0xFF,
        (remote_id >> 16) & 0xFF,
        (remote_id >> 8) & 0xFF,
        remote_id & 0xFF,
    ]
    # Checksum: XOR of every nibble across the (unobfuscated) frame, low 4 bits.
    checksum = 0
    for byte in frame:
        checksum ^= byte ^ (byte >> 4)
    frame[1] |= checksum & 0x0F
    # Obfuscation: chained XOR with the previous byte.
    for index in range(1, 7):
        frame[index] ^= frame[index - 1]
    return frame


def somfy_waveform(
    remote_id: int,
    command: int,
    rolling_code: int,
    repeat_frames: int = SOMFY_REPEAT_FRAMES,
) -> list[int]:
    """Render the RF mark/space timeline for a Somfy RTS transmission.

    Returns signed durations (positive mark, negative space) in the same
    convention as cjoy_waveform, starting with a mark and alternating sign.
    """
    frame = somfy_frame_bytes(remote_id, command, rolling_code)
    segments: list[int] = []

    def add(mark: bool, duration: int) -> None:
        # Manchester produces adjacent same-level half-symbols; coalesce them
        # into one continuous pulse, as they appear on the air.
        signed = duration if mark else -duration
        if segments and (segments[-1] > 0) == (signed > 0):
            segments[-1] += signed
        else:
            segments.append(signed)

    def emit_frame(hw_sync: int, wakeup: bool) -> None:
        if wakeup:
            add(True, SOMFY_WAKEUP_US[0])
            add(False, SOMFY_WAKEUP_US[1])
        for _ in range(hw_sync):
            add(True, SOMFY_HW_SYNC_US)
            add(False, SOMFY_HW_SYNC_US)
        add(True, SOMFY_SW_SYNC_US[0])
        add(False, SOMFY_SW_SYNC_US[1])
        for index in range(56):
            bit = (frame[index // 8] >> (7 - (index % 8))) & 1
            if bit:
                add(False, SOMFY_SYMBOL_US)
                add(True, SOMFY_SYMBOL_US)
            else:
                add(True, SOMFY_SYMBOL_US)
                add(False, SOMFY_SYMBOL_US)
        add(False, SOMFY_INTERFRAME_US)

    emit_frame(SOMFY_FIRST_HW_SYNC, wakeup=True)
    for _ in range(repeat_frames):
        emit_frame(SOMFY_REPEAT_HW_SYNC, wakeup=False)
    return segments


def build_somfy_profile(name: str, remote_id: int) -> DeviceProfile:
    if not 0 <= remote_id < (1 << 24):
        raise CeilingFanError("Somfy remote address must be a 24-bit value")
    return DeviceProfile(
        name=name,
        frequency_hz=SOMFY_FREQUENCY_HZ,
        device_class="roller_blind",
        protocol=ProtocolSpec(
            family="somfy_rts",
            remote_id=remote_id,
            commands=dict(SOMFY_COMMANDS),
        ),
        schema_version=2,
        notes=[
            "Generated from the public Somfy RTS rolling-code protocol adapter.",
            f"Emulated remote address: 0x{remote_id:06X} (24 bits).",
            "Experimental: pair with the motor's PROG button and validate on the "
            "air before trusting it. Somfy transmits at 433.42 MHz.",
        ],
    )
