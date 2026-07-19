from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from .models import CeilingFanError, DeviceProfile
from .waveform import FrameObservation, learn_waveform


@dataclass(frozen=True)
class StaticFingerprint:
    frequency_hz: int
    frame_pulses: int
    gap_us: int

    @classmethod
    def from_observation(cls, observation: "BridgeObservation") -> "StaticFingerprint":
        return cls(
            frequency_hz=observation.frequency_hz,
            frame_pulses=len(observation.frame_us),
            gap_us=observation.gap_us,
        )


@dataclass(frozen=True)
class BridgeObservation:
    frequency_hz: int
    preamble_us: list[int]
    frame_us: list[int]
    gap_us: int
    repetitions: int

    def frame_observation(self) -> FrameObservation:
        return FrameObservation(
            preamble_us=self.preamble_us,
            frame_us=self.frame_us,
            gap_us=self.gap_us,
            repetitions=self.repetitions,
        )


@dataclass(frozen=True)
class FamilyObservation:
    family: str
    remote_id: int
    command: int


_RAW_LINE = re.compile(
    r"CFRAW\s+frequency=(?P<frequency>\d+)\s+"
    r"repetitions=(?P<repetitions>\d+)\s+gap=(?P<gap>\d+)\s+"
    r"preamble=(?P<preamble>none|[-\d,]+)\s+frame=(?P<frame>[-\d,]+)"
)
_FAMILY_LINE = re.compile(
    r"CFLEARN\s+family=(?P<family>[a-z0-9_]+)\s+"
    r"command=0x(?P<command>[0-9A-Fa-f]+)\s+"
    r"remote_id=0x(?P<remote_id>[0-9A-Fa-f]+)"
)


def _durations(value: str) -> list[int]:
    if value == "none":
        return []
    try:
        durations = [int(item) for item in value.split(",")]
    except ValueError as exc:
        raise CeilingFanError("Malformed duration in CFRAW observation") from exc
    if not durations or any(duration == 0 or abs(duration) > 100_000 for duration in durations):
        raise CeilingFanError("CFRAW observation contains invalid pulse durations")
    if any((durations[index] > 0) == (durations[index - 1] > 0) for index in range(1, len(durations))):
        raise CeilingFanError("CFRAW pulse durations do not alternate mark and space")
    return durations


def parse_bridge_observation(line: str) -> BridgeObservation | None:
    match = _RAW_LINE.search(line)
    if match is None:
        return None
    observation = BridgeObservation(
        frequency_hz=int(match.group("frequency")),
        repetitions=int(match.group("repetitions")),
        gap_us=int(match.group("gap")),
        preamble_us=_durations(match.group("preamble")),
        frame_us=_durations(match.group("frame")),
    )
    validate_bridge_observation(observation)
    return observation


def parse_family_observation(line: str) -> FamilyObservation | None:
    match = _FAMILY_LINE.search(line)
    if match is None:
        return None
    return FamilyObservation(
        family=match.group("family"),
        remote_id=int(match.group("remote_id"), 16),
        command=int(match.group("command"), 16),
    )


def validate_bridge_observation(observation: BridgeObservation) -> None:
    for label, durations, allow_empty in (
        ("preamble", observation.preamble_us, True),
        ("frame", observation.frame_us, False),
    ):
        if not durations and not allow_empty:
            raise CeilingFanError(f"CFRAW observation {label} is empty")
        if any(duration == 0 or abs(duration) > 100_000 for duration in durations):
            raise CeilingFanError(
                f"CFRAW observation {label} contains invalid pulse durations"
            )
        if any(
            (durations[index] > 0) == (durations[index - 1] > 0)
            for index in range(1, len(durations))
        ):
            raise CeilingFanError(
                f"CFRAW observation {label} does not alternate mark and space"
            )
    if observation.repetitions < 2:
        raise CeilingFanError("CFRAW observation contains fewer than two repeated frames")
    if len(observation.frame_us) < 4:
        raise CeilingFanError("CFRAW observation frame is too short")
    if observation.frame_us[0] < 0:
        raise CeilingFanError("CFRAW observation must start with an RF mark")
    if not 1_500 <= observation.gap_us <= 100_000:
        raise CeilingFanError("CFRAW observation has an implausible frame gap")


def command_names(commands: list[str] | None) -> list[str]:
    result = list(commands or [])
    result = [name.strip().lower().replace("-", "_") for name in result]
    if not result:
        raise CeilingFanError("Provide at least one --command")
    invalid = [name for name in result if not re.fullmatch(r"[a-z][a-z0-9_]*", name)]
    if invalid:
        raise CeilingFanError("Invalid command labels: " + ", ".join(invalid))
    duplicates = sorted(name for name, count in Counter(result).items() if count > 1)
    if duplicates:
        raise CeilingFanError("Duplicate command labels: " + ", ".join(duplicates))
    return result


def validate_fingerprint(
    fingerprint: StaticFingerprint, observation: BridgeObservation
) -> None:
    problems = []
    if observation.frequency_hz != fingerprint.frequency_hz:
        problems.append(
            f"frequency {observation.frequency_hz}Hz, expected "
            f"{fingerprint.frequency_hz}Hz"
        )
    if len(observation.frame_us) != fingerprint.frame_pulses:
        problems.append(
            f"{len(observation.frame_us)} frame pulses, expected "
            f"{fingerprint.frame_pulses}"
        )
    gap_tolerance = max(500, round(fingerprint.gap_us * 0.2))
    if abs(observation.gap_us - fingerprint.gap_us) > gap_tolerance:
        problems.append(
            f"gap {observation.gap_us}us differs from calibrated "
            f"{fingerprint.gap_us}us by more than {gap_tolerance}us"
        )
    if problems:
        raise CeilingFanError(
            "Observation does not match this learning session's RF fingerprint: "
            + "; ".join(problems)
        )


def build_bridge_profile(
    name: str,
    observations: dict[str, list[BridgeObservation]],
    fingerprint: StaticFingerprint | None = None,
) -> DeviceProfile:
    if not observations or any(not items for items in observations.values()):
        raise CeilingFanError("Every command must contain at least one RF observation")
    frequencies = {
        observation.frequency_hz
        for items in observations.values()
        for observation in items
    }
    if len(frequencies) != 1:
        raise CeilingFanError("All bridge observations must use the same frequency")
    fingerprint = fingerprint or StaticFingerprint.from_observation(
        next(iter(observations.values()))[0]
    )
    for items in observations.values():
        for observation in items:
            validate_fingerprint(fingerprint, observation)
    commands = {
        label: learn_waveform([item.frame_observation() for item in items])
        for label, items in observations.items()
    }
    notes = [
        "Learned from repeated static ASK/OOK frames with the ESP32 + CC1101 bridge.",
        "Relative and unknown commands are exposed as stateless Home Assistant buttons.",
    ]
    notes.append(
        "The RF fingerprint was calibrated from this remote; no model identity or "
        "captured payload was supplied by the software."
    )
    return DeviceProfile(
        name=name,
        frequency_hz=frequencies.pop(),
        commands=commands,
        notes=notes,
    )


def save_bridge_evidence(
    path: Path,
    name: str,
    observations: dict[str, list[BridgeObservation]],
    fingerprint: StaticFingerprint | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "name": name,
        "fingerprint": asdict(fingerprint) if fingerprint is not None else None,
        "commands": {
            label: [asdict(observation) for observation in items]
            for label, items in observations.items()
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_bridge_evidence(
    path: Path,
) -> tuple[str, StaticFingerprint | None, dict[str, list[BridgeObservation]]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported schema")
        name = str(payload["name"])
        raw_fingerprint = payload.get("fingerprint")
        fingerprint = (
            StaticFingerprint(**raw_fingerprint)
            if raw_fingerprint is not None
            else None
        )
        raw_commands = payload["commands"]
        if not isinstance(raw_commands, dict):
            raise ValueError("commands must be a mapping")
        observations = {
            str(label): [BridgeObservation(**item) for item in items]
            for label, items in raw_commands.items()
        }
        for items in observations.values():
            for observation in items:
                validate_bridge_observation(observation)
    except (KeyError, TypeError, ValueError, OSError, yaml.YAMLError) as exc:
        raise CeilingFanError(f"Invalid bridge evidence in {path}: {exc}") from exc
    return name, fingerprint, observations
