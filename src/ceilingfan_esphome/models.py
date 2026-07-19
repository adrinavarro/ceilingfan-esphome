from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CeilingFanError(RuntimeError):
    """A user-facing error with no traceback required."""


@dataclass(frozen=True)
class Capture:
    label: str
    sample_rate: int
    frequency_hz: int
    iq: Any
    source: Path


@dataclass(frozen=True)
class LearnedWaveform:
    preamble_us: list[int]
    frame_us: list[int]
    gap_us: int
    repetitions: int
    trailing_space_us: int
    confidence: float
    observations: int


@dataclass
class DeviceProfile:
    name: str
    frequency_hz: int
    commands: dict[str, LearnedWaveform]
    modulation: str = "ASK/OOK"
    output_power_dbm: int = 0
    schema_version: int = 1
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["commands"] = {
            key: asdict(value) for key, value in sorted(self.commands.items())
        }
        return result

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "DeviceProfile":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise CeilingFanError(f"Unsupported profile schema in {path}")
        commands = {
            key: LearnedWaveform(**value)
            for key, value in raw.get("commands", {}).items()
        }
        if not commands:
            raise CeilingFanError(f"Profile {path} contains no commands")
        return cls(
            name=raw["name"],
            frequency_hz=int(raw["frequency_hz"]),
            modulation=raw.get("modulation", "ASK/OOK"),
            output_power_dbm=int(raw.get("output_power_dbm", 0)),
            schema_version=1,
            notes=list(raw.get("notes", [])),
            commands=commands,
        )

