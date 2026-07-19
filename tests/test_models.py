from pathlib import Path

from ceilingfan_esphome.models import DeviceProfile, LearnedWaveform


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
