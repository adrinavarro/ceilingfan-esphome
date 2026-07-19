from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .models import Capture, CeilingFanError


def metadata_path_for(data_path: Path) -> Path:
    if data_path.name.endswith(".sigmf-data"):
        return data_path.with_name(data_path.name.removesuffix(".sigmf-data") + ".sigmf-meta")
    return data_path.with_suffix(".sigmf-meta")


def data_path_for(meta_path: Path) -> Path:
    if not meta_path.name.endswith(".sigmf-meta"):
        raise CeilingFanError(f"Expected a .sigmf-meta file, got {meta_path}")
    return meta_path.with_name(meta_path.name.removesuffix(".sigmf-meta") + ".sigmf-data")


def write_metadata(
    data_path: Path,
    *,
    label: str,
    sample_rate: int,
    frequency_hz: int,
    gain_db: float,
) -> Path:
    metadata = {
        "global": {
            "core:datatype": "cu8",
            "core:sample_rate": sample_rate,
            "core:version": "1.2.5",
            "core:description": f"ceilingfan-esphome capture: {label}",
            "ceilingfan:label": label,
            "ceilingfan:gain_db": gain_db,
        },
        "captures": [{"core:sample_start": 0, "core:frequency": frequency_hz}],
        "annotations": [],
    }
    path = metadata_path_for(data_path)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return path


def load_capture(meta_path: Path) -> Capture:
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        global_meta = metadata["global"]
        capture_meta = metadata["captures"][0]
    except (OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise CeilingFanError(f"Invalid SigMF metadata in {meta_path}: {exc}") from exc

    datatype = global_meta.get("core:datatype")
    if datatype != "cu8":
        raise CeilingFanError(
            f"Unsupported SigMF datatype {datatype!r} in {meta_path}; expected 'cu8'"
        )

    data_path = data_path_for(meta_path)
    if not data_path.exists():
        raise CeilingFanError(f"Missing sample file {data_path}")
    raw = np.fromfile(data_path, dtype=np.uint8)
    if len(raw) < 2 or len(raw) % 2:
        raise CeilingFanError(f"Invalid interleaved I/Q samples in {data_path}")
    pairs = raw.reshape(-1, 2).astype(np.float32)
    iq = (pairs[:, 0] - 127.5) + 1j * (pairs[:, 1] - 127.5)
    return Capture(
        label=str(global_meta["ceilingfan:label"]),
        sample_rate=int(global_meta["core:sample_rate"]),
        frequency_hz=int(capture_meta["core:frequency"]),
        iq=iq,
        source=meta_path,
    )
