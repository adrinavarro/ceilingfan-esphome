# ceilingfan-esphome

`ceilingfan-esphome` learns static sub-GHz ceiling fan remotes and turns an ESP32 plus
CC1101 into a local Home Assistant bridge.

The project uses an RTL-SDR to discover and record a remote, deterministic Python
code to learn its ASK/OOK waveforms, and ESPHome to expose the resulting fan and
light entities. No cloud account or AI model is required.

## Status

This is an early development release. It currently targets static ASK/OOK remotes
with repeated frames. Rolling codes, encrypted protocols, FSK packet protocols,
and 2.4 GHz remotes are not supported.

## Hardware

- ESP32 DevKit compatible with `esp32dev`.
- CC1101 module for the correct regional frequency band.
- Suitable antenna.
- RTL2832U-based RTL-SDR for discovery and learning.
- Data-capable USB cable.

The reference wiring is:

| CC1101 | ESP32 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| SCK | GPIO18 |
| MOSI / SI | GPIO23 |
| MISO / SO | GPIO19 |
| CSN / SS | GPIO14 |
| GDO0 | GPIO26 |
| GDO2 | GPIO27 |

Never power the CC1101 from 5 V. See [Hardware](docs/hardware.md) before assembly.

## Install

Python 3.11 or later is required. The easiest development installation uses
[`uv`](https://docs.astral.sh/uv/):

```sh
uv sync --extra dev
uv run ceilingfan --help
```

The workflow is deliberately split into three independent phases:

| Phase | Connected hardware | Output |
|---|---|---|
| Learn | RTL-SDR and original remote | `device-profile.yaml` |
| Hardware | Assembled ESP32 + CC1101 over USB | Networked onboarding device |
| Firmware | No computer USB device; ESP32 is reached over Wi-Fi | Final ESPHome bridge |

The RTL-SDR and ESP32 never need to be connected at the same time. See the
[three-phase workflow](docs/workflow.md) for the handoff between phases.

## Workflow

### Phase 1: Learn the remote — RTL-SDR only

The learning phase has no ESP32 dependency. Plug the RTL-SDR into the computer and
check only its tools:

```sh
uv run ceilingfan learn doctor
```

Find the remote frequency while pressing buttons repeatedly:

```sh
uv run ceilingfan learn scan --start 420M --end 450M --duration 30s
```

Inspect `captures/scan.csv` and select the strongest repeatable peak. Regulatory
labels on the remote may already state the frequency.

Record at least three attempts per semantic command:

```sh
uv run ceilingfan learn capture fan_off --frequency 433.92M --attempt 1
uv run ceilingfan learn capture fan_speed_1 --frequency 433.92M --attempt 1
uv run ceilingfan learn capture light_off --frequency 433.92M --attempt 1
uv run ceilingfan learn capture light_on --frequency 433.92M --attempt 1
```

Repeat with `--attempt 2`, `--attempt 3`, and so on. Then learn the profile:

```sh
uv run ceilingfan learn analyze --name "Bedroom ceiling fan"
```

This phase ends when `device-profile.yaml` has been produced. The RTL-SDR can now be
unplugged. Its discovered frequency also tells you which CC1101 module and antenna
band to use.

See [Learning a remote](docs/learning-a-remote.md) for the controlled capture
procedure.

### Phase 2: Prepare the bridge — ESP32 over USB only

Assemble the ESP32 and CC1101, plug the ESP32 into the computer, and check only the
hardware-stage requirements:

```sh
uv run ceilingfan hardware doctor
```

The first flash stores Wi-Fi credentials, enables encrypted ESPHome access and OTA,
and checks the CC1101 over SPI.

```sh
uv run ceilingfan hardware onboard --port /dev/ttyUSB0
```

On macOS, the port will normally look like `/dev/cu.usbserial-*`.

Once onboarding succeeds, unplug the ESP32 from the computer and power it from a
normal USB supply in its intended location. Keep its hostname or IP address.

### Phase 3: Deploy final firmware — OTA over Wi-Fi

Neither RTL-SDR nor ESP32 needs to occupy a computer USB port. The ESP32 must only be
powered and reachable on the local network.

```sh
uv run ceilingfan firmware doctor
uv run ceilingfan firmware build
uv run ceilingfan firmware deploy --device ceilingfan-onboarding.local
```

The generated firmware is written to `firmware/generated.yaml`; edit the profile,
not the generated file.

Finally, trigger each generated entity in Home Assistant and record the observed
result:

```sh
uv run ceilingfan firmware validate
```

The workflow is complete only after every advertised command has passed on the
physical fan.

## Alexa, Google Home, and Matter

The supported automation seam is Home Assistant. Users who already run Home
Assistant can expose the generated fan and light to Alexa, Google Home, Apple Home,
and other Matter controllers through the community-maintained
[Home Assistant Matter Hub](https://github.com/RiDDiX/home-assistant-matter-hub).
Home Assistant Cloud is the simplest officially supported alternative.

See [Voice assistants](docs/voice-assistants.md) for setup guidance, network
requirements, alternatives, and the rationale for not implementing Matter directly
on the ESP32 in the MVP.

## Command labels

The first release recognizes:

- `fan_off`
- `fan_speed_1`, `fan_speed_2`, ...
- `light_off`
- `light_on`

Unknown labels can be learned and retained in a profile, but they do not yet create
Home Assistant entities.

## Design

The stable interface is:

```text
SigMF captures -> device-profile.yaml -> generated ESPHome firmware
```

Raw I/Q data remains local and is excluded from Git. A profile is small, reviewable,
and sufficient to reproduce a static remote. See [Architecture](docs/architecture.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Do not submit Wi-Fi credentials, ESPHome
secrets, personal network details, or unexplained raw recordings.

## License

MIT
