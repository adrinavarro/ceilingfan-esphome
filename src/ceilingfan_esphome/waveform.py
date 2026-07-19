from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median

from .models import CeilingFanError, LearnedWaveform


@dataclass(frozen=True)
class FrameObservation:
    preamble_us: list[int]
    frame_us: list[int]
    gap_us: int
    repetitions: int


def learn_waveform(observations: list[FrameObservation]) -> LearnedWaveform:
    if not observations:
        raise CeilingFanError("No RF observations were provided")
    shape = Counter(
        (len(item.preamble_us), len(item.frame_us)) for item in observations
    ).most_common(1)[0][0]
    matching = [
        item
        for item in observations
        if (len(item.preamble_us), len(item.frame_us)) == shape
    ]
    if not matching:
        raise CeilingFanError("Captures do not contain a consistent waveform")

    def sequence_median(items: list[FrameObservation], attribute: str) -> list[int]:
        sequences = [getattr(item, attribute) for item in items]
        return [
            int(median([sequence[i] for sequence in sequences]))
            for i in range(len(sequences[0]))
        ]

    provisional_preamble = sequence_median(matching, "preamble_us")
    provisional_frame = sequence_median(matching, "frame_us")
    provisional_gap = int(median([item.gap_us for item in matching]))

    def close_sequence(actual: list[int], expected: list[int]) -> bool:
        return all(
            (value > 0) == (target > 0)
            and abs(value - target) <= max(120, round(abs(target) * 0.25))
            for value, target in zip(actual, expected, strict=True)
        )

    matching = [
        item
        for item in matching
        if close_sequence(item.preamble_us, provisional_preamble)
        and close_sequence(item.frame_us, provisional_frame)
        and abs(item.gap_us - provisional_gap) <= max(250, round(provisional_gap * 0.2))
    ]
    if not matching or (len(observations) > 1 and len(matching) < 2):
        raise CeilingFanError(
            "RF observations disagree; capture the same static button for every attempt"
        )

    def median_sequence(attribute: str) -> list[int]:
        return sequence_median(matching, attribute)

    consistency = len(matching) / len(observations)
    repetition_score = min(1.0, float(median([item.repetitions for item in matching])) / 4)
    confidence = round(0.55 * consistency + 0.45 * repetition_score, 3)
    frame = median_sequence("frame_us")
    negative_spaces = [abs(value) for value in frame if value < 0]
    trailing = int(median(negative_spaces)) if negative_spaces else 500
    return LearnedWaveform(
        preamble_us=median_sequence("preamble_us"),
        frame_us=frame,
        gap_us=int(median([item.gap_us for item in matching])),
        repetitions=max(2, int(median([item.repetitions for item in matching]))),
        trailing_space_us=trailing,
        confidence=confidence,
        observations=len(observations),
    )
