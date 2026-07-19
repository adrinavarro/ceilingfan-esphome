from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .models import Capture, CeilingFanError, DeviceProfile
from .sigmf import load_capture
from .waveform import FrameObservation, learn_waveform


def _run_lengths(active: np.ndarray) -> list[tuple[bool, int]]:
    if not len(active):
        return []
    boundaries = np.flatnonzero(active[1:] != active[:-1]) + 1
    starts = np.r_[0, boundaries]
    ends = np.r_[boundaries, len(active)]
    return [(bool(active[start]), int(end - start)) for start, end in zip(starts, ends)]


def _remove_glitches(runs: list[tuple[bool, int]], minimum: int) -> list[tuple[bool, int]]:
    result = runs[:]
    changed = True
    while changed and len(result) >= 3:
        changed = False
        merged: list[tuple[bool, int]] = []
        index = 0
        while index < len(result):
            if (
                0 < index < len(result) - 1
                and result[index][1] < minimum
                and result[index - 1][0] == result[index + 1][0]
            ):
                state = result[index - 1][0]
                length = result[index - 1][1] + result[index][1] + result[index + 1][1]
                if merged:
                    merged.pop()
                merged.append((state, length))
                index += 2
                changed = True
            else:
                merged.append(result[index])
            index += 1
        result = merged
    return result


def extract_pulses(capture: Capture, minimum_pulse_us: int = 40) -> list[int]:
    """Demodulate a cu8 ASK/OOK recording into signed pulse durations."""
    magnitude = np.abs(capture.iq)
    smoothing_samples = max(1, round(capture.sample_rate / 150_000))
    if smoothing_samples > 1:
        kernel = np.ones(smoothing_samples, dtype=np.float32) / smoothing_samples
        magnitude = np.convolve(magnitude, kernel, mode="same")

    noise = float(np.median(magnitude))
    signal = float(np.quantile(magnitude, 0.995))
    if signal <= noise * 1.15 + 1.0:
        raise CeilingFanError(f"No clear OOK signal found in {capture.source}")
    threshold = noise + (signal - noise) * 0.38
    active = magnitude >= threshold
    minimum_samples = max(1, round(minimum_pulse_us * capture.sample_rate / 1_000_000))
    runs = _remove_glitches(_run_lengths(active), minimum_samples)

    while runs and not runs[0][0]:
        runs.pop(0)
    while runs and not runs[-1][0]:
        runs.pop()
    if len(runs) < 6:
        raise CeilingFanError(f"Too few pulses found in {capture.source}")

    return [
        round(length * 1_000_000 / capture.sample_rate) * (1 if state else -1)
        for state, length in runs
    ]


def _gap_threshold(spaces: list[int]) -> int:
    values = sorted(abs(value) for value in spaces)
    if len(values) < 3:
        raise CeilingFanError("Not enough spaces to identify repeated frames")
    candidates = [
        (values[index + 1] / max(values[index], 1), index)
        for index in range(len(values) - 1)
        if values[index + 1] >= 1500
    ]
    if not candidates:
        raise CeilingFanError("No frame gap found; the signal may not be OOK/PWM")
    ratio, index = max(candidates)
    if ratio < 1.8:
        raise CeilingFanError("Frame gap is ambiguous; capture a cleaner button press")
    return round((values[index] + values[index + 1]) / 2)


def observe_frames(pulses: list[int]) -> FrameObservation:
    threshold = _gap_threshold([value for value in pulses if value < 0])
    segments: list[list[int]] = []
    gaps: list[int] = []
    current: list[int] = []
    for duration in pulses:
        if duration < 0 and abs(duration) >= threshold:
            if current:
                segments.append(current)
                current = []
                gaps.append(abs(duration))
        else:
            current.append(duration)
    if current:
        segments.append(current)

    lengths = Counter(len(segment) for segment in segments if len(segment) >= 4)
    if not lengths:
        raise CeilingFanError("No repeated frame candidates found")
    frame_length, _ = lengths.most_common(1)[0]
    frames = [segment for segment in segments if len(segment) == frame_length]
    if len(frames) < 2:
        raise CeilingFanError("Fewer than two matching frames found")

    frame = [int(np.median([candidate[i] for candidate in frames])) for i in range(frame_length)]
    first_frame_index = next(i for i, segment in enumerate(segments) if len(segment) == frame_length)
    preamble: list[int] = []
    if first_frame_index:
        candidate = segments[first_frame_index - 1]
        # Receivers commonly start in the middle of the first repeated frame.
        # Only a short, distinct segment is credible as a real wake-up preamble;
        # a nearly frame-sized segment is detector startup loss and must not be
        # retransmitted.
        if len(candidate) <= 8 and len(candidate) * 4 <= frame_length:
            preamble = candidate
    gap = int(np.median(gaps)) if gaps else 10_000
    return FrameObservation(
        preamble_us=preamble,
        frame_us=frame,
        gap_us=gap,
        repetitions=len(frames),
    )


def learn_profile(meta_paths: list[Path], name: str) -> DeviceProfile:
    if not meta_paths:
        raise CeilingFanError("No .sigmf-meta captures were found")
    captures = [load_capture(path) for path in meta_paths]
    frequencies = Counter(capture.frequency_hz for capture in captures)
    frequency, count = frequencies.most_common(1)[0]
    if count != len(captures):
        raise CeilingFanError("All captures must use the same center frequency")

    grouped: dict[str, list[FrameObservation]] = defaultdict(list)
    for capture in captures:
        grouped[capture.label].append(observe_frames(extract_pulses(capture)))
    commands = {label: learn_waveform(items) for label, items in grouped.items()}
    notes = []
    if any(command.confidence < 0.8 for command in commands.values()):
        notes.append("One or more commands have low confidence and require careful validation.")
    return DeviceProfile(name=name, frequency_hz=frequency, commands=commands, notes=notes)
