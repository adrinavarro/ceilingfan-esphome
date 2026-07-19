from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ceilingfan_esphome.analysis import extract_pulses, learn_profile, observe_frames
from ceilingfan_esphome.models import Capture


SAMPLE_RATE = 1_000_000
FREQUENCY = 433_920_000


def known_protocol_pulses(command: int, repetitions: int = 7) -> list[int]:
    payload = bytes([command, 0x00, 0x77, 0x6D])
    bits = [bool(byte & (1 << bit)) for byte in payload for bit in range(7, -1, -1)]
    bits.append(False)
    pulses = [1053, -7688]
    for repetition in range(repetitions):
        for index, bit in enumerate(bits):
            mark = 355 if bit else 1053
            if index + 1 < len(bits):
                space = 1031 if bits[index + 1] else 337
            else:
                space = 7688 if repetition + 1 < repetitions else 337
            pulses.extend([mark, -space])
    return pulses


def pulse_iq(pulses: list[int], rng_seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(rng_seed)
    amplitudes = [3.0] * 2_000
    for duration in pulses:
        amplitudes.extend(
            [75.0 if duration > 0 else 3.0] * round(abs(duration) * SAMPLE_RATE / 1_000_000)
        )
    amplitudes.extend([3.0] * 2_000)
    amplitude = np.asarray(amplitudes, dtype=np.float32)
    noise_i = rng.normal(0, 1.0, len(amplitude))
    noise_q = rng.normal(0, 1.0, len(amplitude))
    return (amplitude + noise_i) + 1j * noise_q


def write_sigmf(directory: Path, label: str, attempt: int, pulses: list[int]) -> Path:
    iq = pulse_iq(pulses, attempt)
    i_values = np.clip(np.real(iq) + 127.5, 0, 255).astype(np.uint8)
    q_values = np.clip(np.imag(iq) + 127.5, 0, 255).astype(np.uint8)
    interleaved = np.column_stack([i_values, q_values]).reshape(-1)
    stem = f"{label}-{attempt:02d}"
    data_path = directory / f"{stem}.sigmf-data"
    meta_path = directory / f"{stem}.sigmf-meta"
    interleaved.tofile(data_path)
    metadata = {
        "global": {
            "core:datatype": "cu8",
            "core:sample_rate": SAMPLE_RATE,
            "core:version": "1.2.5",
            "ceilingfan:label": label,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": FREQUENCY}],
        "annotations": [],
    }
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    return meta_path


def test_extracts_repeated_known_protocol() -> None:
    capture = Capture(
        label="fan_off",
        sample_rate=SAMPLE_RATE,
        frequency_hz=FREQUENCY,
        iq=pulse_iq(known_protocol_pulses(0xE2)),
        source=Path("synthetic.sigmf-meta"),
    )

    pulses = extract_pulses(capture)
    observation = observe_frames(pulses)

    assert observation.repetitions >= 6
    assert 7_300 <= observation.gap_us <= 8_100
    assert len(observation.preamble_us) == 1
    assert len(observation.frame_us) >= 64


def test_learns_multiple_semantic_commands(tmp_path: Path) -> None:
    commands = {
        "fan_off": 0xE2,
        "fan_speed_1": 0xF5,
        "light_off": 0xDB,
        "light_on": 0xD4,
    }
    paths = [
        write_sigmf(tmp_path, label, attempt, known_protocol_pulses(command))
        for label, command in commands.items()
        for attempt in (1, 2)
    ]

    profile = learn_profile(paths, "Test ceiling fan")

    assert profile.frequency_hz == FREQUENCY
    assert set(profile.commands) == set(commands)
    assert all(command.confidence >= 0.9 for command in profile.commands.values())
    assert all(command.observations == 2 for command in profile.commands.values())
