from pathlib import Path

import pytest

from ceilingfan_esphome.models import (
    CeilingFanError,
    DeviceProfile,
    LearnedWaveform,
    ProtocolSpec,
)


def _waveform() -> LearnedWaveform:
    return LearnedWaveform(
        preamble_us=[],
        frame_us=[1000, -300, 300, -1000],
        gap_us=7000,
        repetitions=4,
        trailing_space_us=300,
        confidence=0.95,
        observations=3,
    )


def test_profile_round_trip(tmp_path: Path) -> None:
    profile = DeviceProfile(
        name="Example fan",
        frequency_hz=433_920_000,
        commands={
            "fan_off": LearnedWaveform(
                preamble_us=[],
                frame_us=[1000, -300, 300, -1000],
                gap_us=7000,
                repetitions=4,
                trailing_space_us=300,
                confidence=0.95,
                observations=3,
            )
        },
    )
    path = tmp_path / "profile.yaml"

    profile.save(path)
    loaded = DeviceProfile.load(path)

    assert loaded == profile


def test_structured_profile_round_trip(tmp_path: Path) -> None:
    profile = DeviceProfile(
        name="CJOY fan",
        frequency_hz=433_920_000,
        protocol=ProtocolSpec(
            family="cjoy",
            remote_id=0x175D0310,
            commands={"fan_off": 0x1F, "fan_speed_1": 0x2B},
        ),
        schema_version=2,
    )
    path = tmp_path / "cjoy.yaml"

    profile.save(path)
    loaded = DeviceProfile.load(path)

    assert loaded == profile
    assert loaded.command_names() == ["fan_off", "fan_speed_1"]


def test_profiles_declare_their_device_class(tmp_path: Path) -> None:
    profile = DeviceProfile(
        name="Example fan",
        frequency_hz=433_920_000,
        commands={"fan_off": _waveform()},
    )
    path = tmp_path / "profile.yaml"
    profile.save(path)

    assert profile.device_class == "ceiling_fan"
    assert "device_class: ceiling_fan" in path.read_text(encoding="utf-8")


def test_profiles_written_before_device_class_default_to_ceiling_fan(
    tmp_path: Path,
) -> None:
    profile = DeviceProfile(
        name="Example fan",
        frequency_hz=433_920_000,
        commands={"fan_off": _waveform()},
    )
    path = tmp_path / "profile.yaml"
    profile.save(path)
    legacy = "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("device_class:")
    )
    path.write_text(legacy + "\n", encoding="utf-8")

    loaded = DeviceProfile.load(path)

    assert loaded.device_class == "ceiling_fan"
    assert loaded == profile


def test_unknown_device_classes_fail_loudly(tmp_path: Path) -> None:
    with pytest.raises(CeilingFanError, match="device class 'cover'"):
        DeviceProfile(
            name="Blinds",
            frequency_hz=433_920_000,
            device_class="cover",
            commands={"open": _waveform()},
        )

    profile = DeviceProfile(
        name="Example fan",
        frequency_hz=433_920_000,
        commands={"fan_off": _waveform()},
    )
    path = tmp_path / "profile.yaml"
    profile.save(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "device_class: ceiling_fan", "device_class: cover"
        ),
        encoding="utf-8",
    )

    with pytest.raises(CeilingFanError, match="device class 'cover'"):
        DeviceProfile.load(path)
