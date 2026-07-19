from __future__ import annotations

import pytest

from ceilingfan_esphome.models import CeilingFanError
from ceilingfan_esphome.protocols import (
    CJOY_COMMANDS,
    INSPIRE_PRO_COMMANDS,
    build_cjoy_profile,
    build_inspire_pro_profile,
    cjoy_tail,
    cjoy_waveform,
)


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
