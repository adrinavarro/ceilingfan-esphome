from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CeilingFanError(RuntimeError):
    """A user-facing error with no traceback required."""


# The kinds of physical installations a device profile can describe. It says
# *what the thing is*, orthogonal to the protocol family (how it is addressed):
# a roller blind might speak Somfy RTS, a ceiling fan Inspire Pro or CJOY.
# Awnings and roller shutters would be sibling classes sharing the same cover
# entity mapping. Unknown classes fail loudly, like all uncertain evidence here.
SUPPORTED_DEVICE_CLASSES = ("ceiling_fan", "roller_blind")


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


@dataclass(frozen=True)
class ProtocolSpec:
    family: str
    remote_id: int
    commands: dict[str, int]


@dataclass
class DeviceProfile:
    name: str
    frequency_hz: int
    device_class: str = "ceiling_fan"
    commands: dict[str, LearnedWaveform] = field(default_factory=dict)
    protocol: ProtocolSpec | None = None
    modulation: str = "ASK/OOK"
    output_power_dbm: int = 0
    schema_version: int = 1
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.device_class not in SUPPORTED_DEVICE_CLASSES:
            raise CeilingFanError(
                f"Unsupported device class '{self.device_class}'; supported "
                "classes: " + ", ".join(SUPPORTED_DEVICE_CLASSES)
            )
        if self.protocol is not None:
            if self.commands:
                raise CeilingFanError(
                    "A structured profile cannot also contain raw waveform commands"
                )
            self.schema_version = 2

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "device_class": self.device_class,
            "frequency_hz": self.frequency_hz,
        }
        if self.protocol is None:
            result["commands"] = {
                key: asdict(value) for key, value in sorted(self.commands.items())
            }
        else:
            result["protocol"] = {
                "family": self.protocol.family,
                "remote_id": self.protocol.remote_id,
                "commands": dict(sorted(self.protocol.commands.items())),
            }
        result.update(
            {
                "modulation": self.modulation,
                "output_power_dbm": self.output_power_dbm,
                "schema_version": self.schema_version,
                "notes": self.notes,
            }
        )
        return result

    def command_names(self) -> list[str]:
        source = self.protocol.commands if self.protocol is not None else self.commands
        return sorted(source)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.to_dict(), sort_keys=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "DeviceProfile":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") not in {1, 2}:
            raise CeilingFanError(f"Unsupported profile schema in {path}")
        schema_version = int(raw["schema_version"])
        commands: dict[str, LearnedWaveform] = {}
        protocol = None
        if schema_version == 1:
            commands = {
                key: LearnedWaveform(**value)
                for key, value in raw.get("commands", {}).items()
            }
            if not commands:
                raise CeilingFanError(f"Profile {path} contains no commands")
        else:
            value = raw.get("protocol")
            if not isinstance(value, dict) or not value.get("commands"):
                raise CeilingFanError(f"Profile {path} contains no protocol commands")
            protocol = ProtocolSpec(
                family=str(value["family"]),
                remote_id=int(value["remote_id"]),
                commands={key: int(code) for key, code in value["commands"].items()},
            )
        return cls(
            name=raw["name"],
            # Profiles written before the field existed are all ceiling fans.
            device_class=str(raw.get("device_class", "ceiling_fan")),
            frequency_hz=int(raw["frequency_hz"]),
            commands=commands,
            protocol=protocol,
            modulation=raw.get("modulation", "ASK/OOK"),
            output_power_dbm=int(raw.get("output_power_dbm", 0)),
            schema_version=schema_version,
            notes=list(raw.get("notes", [])),
        )
