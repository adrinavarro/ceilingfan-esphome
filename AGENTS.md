# Agent guide

`ceilingfan-esphome` turns an ESP32 + CC1101 into a local ESPHome bridge for
sub-GHz ceiling fans: it learns a fan's remote, generates firmware, and controls
the fan over the encrypted ESPHome native API. Home Assistant is optional.

## Commands

```sh
uv sync --extra dev          # install for development (Python >= 3.11)
uv run pytest                # full test suite; must pass before a PR
uv run ruff check .          # lint; must pass before a PR
uv run ceilingfan --help     # CLI entry point; one subcommand per phase
```

Dependency extras are intentional seams: the base install (control only) needs
just `aioesphomeapi` + `PyYAML`; `firmware` adds the ESPHome CLI; `research`
adds numpy for the RTL-SDR laboratory. Keep numpy imports out of the normal
workflow modules — `research` code imports lazily via `_import_research` in
`cli.py`.

## Where things live

- `src/ceilingfan_esphome/cli.py` — argument parsing and phase dispatch.
- `src/ceilingfan_esphome/bridge_learning.py` — parses `CFRAW`/`CFLEARN` log
  lines from the learning firmware into observations and profiles.
- `src/ceilingfan_esphome/protocols.py` — structured protocol families
  (Inspire Pro, CJOY, Somfy RTS) that synthesize profiles from a remote
  identity. Somfy RTS is the first non-fan family (`device_class: roller_blind`)
  and, like CJOY, is generated with a persistent per-installation counter.
- `src/ceilingfan_esphome/waveform.py` — numpy-free timing math shared by
  bridge learning and RTL analysis (`FrameObservation`, `learn_waveform`).
- `src/ceilingfan_esphome/analysis.py` / `sigmf.py` — RTL-SDR research track;
  the only modules that import numpy.
- `src/ceilingfan_esphome/models.py` — `DeviceProfile`, the stable seam.
- `src/ceilingfan_esphome/esphome.py` — renders profiles into ESPHome YAML and
  wraps the `esphome` CLI; `firmware/learning.yaml` is the learning firmware.
- `src/ceilingfan_esphome/control.py` — encrypted native-API client used by
  `ceilingfan control` (no Home Assistant involved).
- `docs/` — user docs; `docs/architecture.md` is the design overview and
  `docs/protocol-catalog.md` indexes decoded protocol evidence.

## Domain language

Read `CONTEXT.md` before renaming or introducing terms; it defines the
vocabulary (RF Bridge, Device Profile, Protocol Family, Remote Identity,
Absolute/Relative/Dynamic Command...) and the terms to avoid.

## Invariants

- Everything crosses the `device profile -> generated firmware` seam. Learning
  adapters and the firmware generator must not know about each other.
- One profile describes one physical fan installation, never a fan model.
- Learning must fail loudly on dynamic or ambiguous evidence; never turn
  uncertain captures into a profile.
- The CLI controls entity IDs, never RF internals; keep one capability model
  for humans, agents, and Home Assistant.
- Never commit `firmware/secrets.yaml`, generated firmware, `.sigmf-data`
  recordings, or personal network details.
