from pathlib import Path

from ceilingfan_esphome.models import DeviceProfile, LearnedWaveform, ProtocolSpec


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
