# Contributing

Thank you for helping make local ceiling fan control easier to reproduce.

## Before opening a pull request

1. Run `uv run pytest` and `uv run ruff check .` (both come with `uv sync --extra dev`).
2. Run `uv run ceilingfan --help` and inspect each phase help page.
3. Document new behavior in English.
4. Add synthetic or minimized fixtures for new learning behavior.
5. State which physical fan, remote, frequency, and commands were validated.

Do not commit `.sigmf-data`, `secrets.yaml`, generated firmware, personal IP
addresses, or raw Home Assistant backups. Large recordings may be shared separately
after their metadata and privacy implications have been reviewed.

## Adding a fan

A fan profile is publishable only when every advertised command has a recorded
physical validation. One tested remote proves one working unit, not an entire model
family. A compatibility claim for a model should include a second independent unit
or clearly state the limitation.

## Adding a protocol

Keep the public interface as captures to profile to firmware. New protocol knowledge
belongs behind that seam. Include a failing fixture first, a minimal adapter, and
evidence that replayed commands work on hardware.
