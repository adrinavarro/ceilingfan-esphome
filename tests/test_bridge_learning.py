from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ceilingfan_esphome.bridge_learning import (
    BridgeObservation,
    FamilyObservation,
    StaticFingerprint,
    build_bridge_profile,
    command_names,
    load_bridge_evidence,
    parse_bridge_observation,
    parse_family_observation,
    save_bridge_evidence,
    validate_fingerprint,
)
from ceilingfan_esphome.models import CeilingFanError


def observation(frame: list[int] | None = None) -> BridgeObservation:
    return BridgeObservation(
        frequency_hz=433_920_000,
        preamble_us=[],
        frame_us=frame or [300, -700, 700, -300, 300],
        gap_us=9_050,
        repetitions=7,
    )


def family_observation(gap_us: int) -> BridgeObservation:
    return BridgeObservation(
        frequency_hz=433_920_000,
        preamble_us=[],
        frame_us=[300, -700] * 32 + [300],
        gap_us=gap_us,
        repetitions=6,
    )


def test_parses_machine_readable_bridge_observation_from_esphome_log() -> None:
    line = (
        "[I][ceilingfan.learn:123]: CFRAW frequency=433920000 repetitions=7 "
        "gap=9050 preamble=none frame=300,-700,700,-300,300\x1b[0m"
    )

    result = parse_bridge_observation(line)

    assert result == observation()


def test_parses_a_known_family_observation_for_automatic_fast_path() -> None:
    line = (
        "[I][ceilingfan.learn]: CFLEARN family=inspire_pro command=0xE2 "
        "remote_id=0x05A243E matches=7"
    )

    assert parse_family_observation(line) == FamilyObservation(
        family="inspire_pro", remote_id=0x05A243E, command=0xE2
    )


def test_rejects_non_alternating_bridge_durations() -> None:
    line = (
        "CFRAW frequency=433920000 repetitions=7 gap=9050 "
        "preamble=none frame=300,700,-300,-700"
    )

    with pytest.raises(CeilingFanError, match="alternate"):
        parse_bridge_observation(line)


def test_calibrates_an_identity_agnostic_fingerprint_from_the_remote() -> None:
    fingerprint = StaticFingerprint.from_observation(family_observation(9_050))

    assert fingerprint == StaticFingerprint(433_920_000, 65, 9_050)
    validate_fingerprint(fingerprint, family_observation(9_200))

    with pytest.raises(CeilingFanError, match="fingerprint"):
        validate_fingerprint(fingerprint, family_observation(4_360))


def test_custom_commands_are_normalized_and_duplicates_rejected() -> None:
    assert command_names(["Fan-Toggle", "my_button"]) == [
        "fan_toggle",
        "my_button",
    ]
    with pytest.raises(CeilingFanError, match="Duplicate"):
        command_names(["fan-toggle", "fan_toggle"])


def test_builds_raw_profile_from_bridge_observations() -> None:
    profile = build_bridge_profile(
        "Nashi bedroom",
        {
            "fan_toggle": [observation()],
            "fan_speed_1": [observation([700, -300, 300, -700, 700])],
        },
    )

    assert profile.frequency_hz == 433_920_000
    assert set(profile.commands) == {"fan_toggle", "fan_speed_1"}
    assert profile.commands["fan_toggle"].repetitions == 7
    assert profile.commands["fan_toggle"].confidence == 1.0


def test_rejects_attempts_that_captured_different_button_waveforms() -> None:
    first = observation([300, -700, 700, -300, 300])
    second = observation([700, -300, 300, -700, 700])

    with pytest.raises(CeilingFanError, match="disagree"):
        build_bridge_profile("Wrong captures", {"light_toggle": [first, second]})


def test_saves_reviewable_bridge_evidence(tmp_path: Path) -> None:
    path = tmp_path / "nashi.observations.yaml"

    fingerprint = StaticFingerprint.from_observation(observation())
    save_bridge_evidence(
        path,
        "Nashi bedroom",
        {"fan_toggle": [observation()]},
        fingerprint=fingerprint,
    )

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["commands"]["fan_toggle"][0]["gap_us"] == 9_050

    name, loaded_fingerprint, loaded = load_bridge_evidence(path)
    assert name == "Nashi bedroom"
    assert loaded_fingerprint == fingerprint
    assert loaded == {"fan_toggle": [observation()]}
