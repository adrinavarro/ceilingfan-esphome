from __future__ import annotations

import pytest

from ceilingfan_esphome.models import CeilingFanError
from ceilingfan_esphome.protocols import (
    CJOY_COMMANDS,
    INSPIRE_PRO_COMMANDS,
    SOMFY_COMMANDS,
    build_cjoy_profile,
    build_inspire_pro_profile,
    build_somfy_profile,
    cjoy_tail,
    cjoy_waveform,
    somfy_frame_bytes,
    somfy_waveform,
)


def _somfy_deobfuscate(frame: list[int]) -> list[int]:
    """Independent inverse of the chained-XOR obfuscation, for verification."""
    return [frame[0]] + [frame[i] ^ frame[i - 1] for i in range(1, 7)]


def test_builds_complete_inspire_pro_profile() -> None:
    profile = build_inspire_pro_profile("Bedroom fan", 0x080ED61)

    assert profile.frequency_hz == 433_920_000
    assert set(profile.commands) == set(INSPIRE_PRO_COMMANDS)
    assert len(profile.commands["fan_off"].frame_us) == 66


def test_inspire_pro_waveform_contains_command_and_25_bit_identity() -> None:
    remote_id = 0x080ED61
    profile = build_inspire_pro_profile("Bedroom fan", remote_id)
    marks = profile.commands["fan_speed_2"].frame_us[::2]
    bits = "".join("1" if mark < 700 else "0" for mark in marks)

    assert int(bits[:8], 2) == 0xED
    assert int(bits[8:], 2) == remote_id


def test_rejects_out_of_range_inspire_pro_identity() -> None:
    with pytest.raises(CeilingFanError, match="25-bit"):
        build_inspire_pro_profile("Invalid", 1 << 25)


def test_cjoy_encoder_reproduces_every_observed_phase_tail() -> None:
    observed = {
        ("fan_off", 1): 0x4CA,
        ("fan_speed_1", 3): 0x0C6,
        ("fan_speed_2", 0): 0x7BE,
        ("fan_speed_2", 2): 0x2D6,
        ("fan_speed_3", 0): 0x77E,
        ("fan_speed_4", 1): 0x54A,
        ("fan_speed_5", 2): 0x34E,
        ("fan_speed_6", 3): 0x1BE,
        ("light_toggle", 0): 0x63E,
        ("dimmer_down", 1): 0x4FA,
        ("dimmer_up", 2): 0x35E,
        ("light_toggle", 3): 0x09E,
        ("dimmer_down", 0): 0x7F6,
        ("dimmer_up", 1): 0x53A,
        ("fan_off", 2): 0x2AE,
        ("fan_off", 3): 0x166,
    }

    for (label, phase), expected in observed.items():
        assert cjoy_tail(CJOY_COMMANDS[label], phase) == expected


def test_builds_structured_cjoy_profile() -> None:
    profile = build_cjoy_profile("CJOY bedroom", 0x175D0310)

    assert profile.frequency_hz == 433_920_000
    assert profile.commands == {}
    assert profile.protocol is not None
    assert profile.protocol.family == "cjoy"
    assert profile.protocol.remote_id == 0x175D0310
    assert profile.protocol.commands == CJOY_COMMANDS
    assert profile.command_names() == sorted(CJOY_COMMANDS)
    assert profile.schema_version == 2


def test_cjoy_waveform_contains_five_identical_captured_frames() -> None:
    remote_id = 0x175D0310
    waveform = cjoy_waveform(remote_id, CJOY_COMMANDS["fan_off"], 1)

    assert waveform[:4] == [8805, -2860, 7394, -1083]
    assert len(waveform) == 502
    frames = [
        waveform[2 + offset * 100 : 2 + (offset + 1) * 100]
        for offset in range(5)
    ]
    assert all(frame == frames[0] for frame in frames[1:])
    bits = "".join("1" if mark > 550 else "0" for mark in frames[0][2::2])
    assert int(bits[:32], 2) == remote_id
    assert int(bits[32:38], 2) == CJOY_COMMANDS["fan_off"]
    assert int(bits[38:], 2) == 0x4CA


def test_rejects_out_of_range_cjoy_identity() -> None:
    with pytest.raises(CeilingFanError, match="32-bit"):
        build_cjoy_profile("Invalid", 1 << 32)


def test_somfy_frame_recovers_its_fields_after_deobfuscation() -> None:
    remote_id = 0x112233
    rolling_code = 0x00A5
    frame = somfy_frame_bytes(remote_id, SOMFY_COMMANDS["cover_up"], rolling_code)

    plain = _somfy_deobfuscate(frame)

    assert plain[0] == 0xA7
    assert plain[1] >> 4 == SOMFY_COMMANDS["cover_up"]
    assert (plain[2] << 8) | plain[3] == rolling_code
    assert (plain[4] << 16) | (plain[5] << 8) | plain[6] == remote_id


def test_somfy_checksum_is_valid_over_the_plain_frame() -> None:
    frame = somfy_frame_bytes(0xABCDEF, SOMFY_COMMANDS["cover_down"], 0x1234)
    plain = _somfy_deobfuscate(frame)

    # The receiver re-derives the checksum over the frame with a zeroed nibble
    # and compares it to the stored one.
    stored = plain[1] & 0x0F
    zeroed = list(plain)
    zeroed[1] &= 0xF0
    checksum = 0
    for byte in zeroed:
        checksum ^= byte ^ (byte >> 4)
    assert stored == checksum & 0x0F


def test_somfy_rolling_code_changes_the_frame() -> None:
    first = somfy_frame_bytes(0x112233, SOMFY_COMMANDS["cover_up"], 5)
    second = somfy_frame_bytes(0x112233, SOMFY_COMMANDS["cover_up"], 6)

    assert first != second


def test_somfy_waveform_is_a_clean_mark_space_timeline() -> None:
    waveform = somfy_waveform(0x112233, SOMFY_COMMANDS["cover_up"], 1)

    assert waveform[0] > 0  # starts on a mark
    assert waveform[0] == 9415  # wake-up pulse
    assert len(waveform) % 2 == 0  # whole mark/space pairs
    # Signs strictly alternate (marks positive, spaces negative).
    assert all(
        (waveform[i] > 0) != (waveform[i + 1] > 0) for i in range(len(waveform) - 1)
    )
    assert all(duration != 0 for duration in waveform)
    assert waveform[-1] < 0  # ends on the inter-frame silence


def test_somfy_rejects_out_of_range_inputs() -> None:
    with pytest.raises(CeilingFanError, match="24-bit"):
        somfy_frame_bytes(1 << 24, SOMFY_COMMANDS["cover_up"], 0)
    with pytest.raises(CeilingFanError, match="command"):
        somfy_frame_bytes(0x112233, 0x3, 0)
    with pytest.raises(CeilingFanError, match="16-bit"):
        somfy_frame_bytes(0x112233, SOMFY_COMMANDS["cover_up"], 1 << 16)


def test_builds_structured_somfy_profile() -> None:
    profile = build_somfy_profile("Persiana salon", 0x112233)

    assert profile.frequency_hz == 433_420_000
    assert profile.device_class == "roller_blind"
    assert profile.protocol is not None
    assert profile.protocol.family == "somfy_rts"
    assert profile.protocol.remote_id == 0x112233
    assert profile.protocol.commands == SOMFY_COMMANDS
    assert profile.schema_version == 2


def test_rejects_out_of_range_somfy_identity() -> None:
    with pytest.raises(CeilingFanError, match="24-bit"):
        build_somfy_profile("Invalid", 1 << 24)
