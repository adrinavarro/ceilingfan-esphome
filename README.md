# ceilingfan-esphome

`ceilingfan-esphome` turns an ESP32 plus CC1101 (about EUR 18 in parts) into a
local RF bridge for sub-GHz ceiling fans. It listens to the fan's original
remote once, learns its commands, and then exposes the fan and light as ESPHome
entities you can control from a CLI, a phone browser, a local AI agent, or Home
Assistant — all on your own network, with no cloud account.

The original remote keeps working: learning is passive and never touches the
fan's pairing. The bridge adds control paths; it does not replace anything.

## Quickstart

```sh
# 0. Wire the CC1101 to the ESP32 (table below) and plug it in over USB.
uv sync --extra firmware

# 1. Flash the learning firmware and store Wi-Fi credentials (USB, once).
uv run ceilingfan hardware onboard --port /dev/ttyUSB0

# 2. Learn each fan from its own remote (over Wi-Fi, one wizard per fan).
uv run ceilingfan learn wizard --name "Bedroom fan"

# 3. Generate and install the final firmware over the air.
uv run ceilingfan firmware deploy --bridge-name "Home RF bridge" \
  --device ceilingfan-learning.local --web-ui

# 4. Control it — no Home Assistant required.
uv run ceilingfan control fan --device home-rf-bridge.local \
  --entity bedroom_fan --state on --speed 3
```

On macOS the serial port normally looks like `/dev/cu.usbserial-*`. Each
command's phase has a `doctor` subcommand (`hardware doctor`, `learn doctor`,
`firmware doctor`) that checks its requirements first. `firmware deploy` picks
up every profile in `profiles/` automatically; `--web-ui` additionally serves a
phone-friendly control page at `http://home-rf-bridge.local`.

## Is my fan supported?

- **Inspire Aveiro Pro, Bora Pro, Tavira Pro, or an equivalent Arteconfort
  model**: yes, with fast onboarding. One recognized button press reveals the
  remote's identity and the wizard synthesizes the complete verified command
  set (fan off, six speeds, light off, eight brightness levels).
- **Any other static 433.92 MHz ASK/OOK remote** (each button always sends the
  same waveform — includes Inspire Nashi and YK8078): yes, button by button.
  The wizard calibrates an RF fingerprint from your first press and learns each
  control you name. No model preset is needed.
- **CJOY remotes**: recognized and supported through an experimental adapter
  that generates the protocol's rolling four-phase checksum. Marked
  experimental until replay is validated against its physical receiver.
- **Rolling-code, encrypted, FSK packet, or 2.4 GHz remotes**: not supported.
  The same applies to remotes that send each button event only once — at least
  two repeated frames are required as anti-noise evidence (holding the button
  usually provides them). The wizard detects unstable waveforms and refuses to
  build a misleading profile rather than guessing.

All families cataloged so far use 433.92 MHz ASK/OOK — an observation about
these fans, not an industry guarantee. See the
[protocol catalog](docs/protocol-catalog.md) for the evidence behind each
family and [Learning a remote](docs/learning-a-remote.md) for the procedure.

> **An RTL-SDR is not required.** The ESP32 + CC1101 does all normal learning.
> An RTL-SDR is only an optional research instrument for investigating a
> protocol the bridge does not yet understand
> ([advanced research](docs/advanced-rtl-research.md)).

## Hardware

Normal setup requires:

- an ESP32 DevKit compatible with `esp32dev`;
- a CC1101 module and antenna for the fan's band (433 MHz for the current catalog);
- eight female-to-female Dupont wires;
- a data-capable USB cable and a USB power supply;
- the fan's original remote.

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

Never power the CC1101 from 5 V. See the complete [shopping list and assembly
notes](docs/hardware.md), including a reference purchase at about EUR 18.

## Install

Python 3.11 or later is required. For the full workflow (learning, firmware),
clone the repository and use [`uv`](https://docs.astral.sh/uv/):

```sh
uv sync --extra firmware
uv run ceilingfan --help
```

Dependencies are split so each role installs only what it uses:

| Install | Gets | For |
|---|---|---|
| base (no extras) | `aioesphomeapi`, `PyYAML` | Controlling a deployed bridge |
| `--extra firmware` | + the ESPHome CLI | Flashing, learning, and deploying |
| `--extra research` | + `numpy` | The optional RTL-SDR laboratory |
| `--extra dev` | + `pytest`, `ruff`, `numpy` | Contributing |

To only *operate* an already-deployed bridge from another machine, container,
or agent host, install the CLI directly from GitHub — no checkout, no ESPHome,
no numpy:

```sh
uv tool install git+https://github.com/adrinavarro/ceilingfan-esphome
ceilingfan control list --device home-rf-bridge.local --json
```

## Normal workflow

The order follows the hardware you have in hand:

| Stage | Connection to the computer | Result |
|---|---|---|
| Assemble and onboard | ESP32 + CC1101 over USB | Wi-Fi and OTA learning bridge |
| Learn | Bridge powered and reached over Wi-Fi | One profile per fan installation |
| Deploy | Bridge reached over Wi-Fi | Final multi-fan ESPHome firmware |
| Operate | Bridge powered on the local network | CLI, web UI, agent, or Home Assistant |

USB is mandatory only for the first flash; everything afterwards travels over
Wi-Fi, and USB remains a recovery path if networking or OTA fails.

### 1. Assemble and onboard over USB

Wire the ESP32 and CC1101, connect the ESP32 to the computer, and run:

```sh
uv run ceilingfan hardware doctor
uv run ceilingfan hardware onboard --port /dev/ttyUSB0
```

Onboarding installs the *learning firmware*: it checks the CC1101, stores Wi-Fi
credentials, enables encrypted ESPHome access and OTA, and starts the CC1101
receiver. The bridge comes up as `ceilingfan-learning.local` and can then run
from an ordinary USB power supply in its intended location.

### 2. Learn each fan with the wizard

One command learns any supported remote — the wizard identifies the remote
from a single button press before asking for anything else:

```sh
uv run ceilingfan learn doctor
uv run ceilingfan learn wizard --name "Bedroom fan"
```

Press any button once when prompted. An Inspire Pro press synthesizes the
complete verified command set from the remote's identity — no buttons need
naming; a CJOY press selects its experimental stateful adapter. Any other
static remote falls into the button-by-button flow: that first press calibrates
the session fingerprint, then the wizard asks you to name and press each
control. Profiles land in `profiles/<name-slug>.yaml` unless `--output` says
otherwise. For a scripted session, repeat `--command` with semantic labels:

```sh
uv run ceilingfan learn wizard \
  --name "Other fan" \
  --command fan_toggle \
  --command fan_speed_1 \
  --command light_toggle
```

The wizard warns immediately when a label set will not produce a fan or light
entity (for example `fan_speed_1` without `fan_off`, or a typo like
`fan_speed1`), before any buttons are pressed.

Do not press the fan receiver's pairing button — learning only listens to
normal remote traffic. Each physical fan needs its own profile and remote
identity, even when several fans are the same model: run the wizard once per
fan, writing every profile into `profiles/`. Interrupted sessions can continue
with `--resume`. See [Learning a remote](docs/learning-a-remote.md) for the
full procedure, validation checklist, and diagnostic commands.

### 3. Generate and deploy final firmware over OTA

With every profile in `profiles/`, no repetition is needed — the firmware
commands pick them all up (or pass explicit `--profile` options):

```sh
uv run ceilingfan firmware doctor
uv run ceilingfan firmware deploy \
  --bridge-name "Home RF bridge" \
  --device ceilingfan-learning.local \
  --web-ui
```

Each profile creates separate ESPHome fan, light, and stateless button
entities; the local CLI, web UI, and Home Assistant all consume that same
entity boundary. Transmissions share one queue, and the bridge applies each
profile's frequency and output power immediately before sending. All profiles
on one bridge must use the same modulation, and the CC1101 module and antenna
must cover every configured band.

The generated file is `firmware/generated.yaml`. Edit profiles, not that file.
The deploy finishes by printing the bridge's final hostname (derived from the
bridge name, `home-rf-bridge.local` here). Then test every entity against its
intended physical fan and record the result — with `--device`, validate sends
each command itself and only asks what physically happened:

```sh
uv run ceilingfan firmware validate --device home-rf-bridge.local
```

### Adding a fan later

ESPHome entities are compiled in, so a new fan means regenerating firmware —
still entirely over the air:

```sh
uv run ceilingfan learn prepare --device home-rf-bridge.local
uv run ceilingfan learn wizard --name "Guest room fan"
uv run ceilingfan firmware deploy --bridge-name "Home RF bridge" \
  --device ceilingfan-learning.local --web-ui
```

`learn prepare` temporarily reinstalls the learning firmware (normal control is
unavailable while it runs); the final deploy picks up all old and new profiles
from `profiles/`. See [One bridge for a multi-fan home](docs/multi-fan-home.md)
for a complete five-fan example.

## Control without Home Assistant

The deployed bridge accepts encrypted local commands directly. If the
hostname is unknown, `control discover` finds bridges over mDNS:

```sh
uv run ceilingfan control discover
uv run ceilingfan control list --device home-rf-bridge.local
uv run ceilingfan control fan \
  --device home-rf-bridge.local \
  --entity bedroom_fan \
  --state on \
  --speed 3
```

Every command supports `--json` for local automation or an agent such as
OpenClaw, including machine-readable errors. The encryption key comes from
`firmware/secrets.yaml` or the `CEILINGFAN_API_KEY` environment variable; it is
never passed on the command line. Setting `CEILINGFAN_DEVICE` makes `--device`
optional, so daily use shrinks to `ceilingfan control fan --entity bedroom_fan
--state on`.

Deploying with `--web-ui` also serves a control page from the bridge itself at
`http://home-rf-bridge.local` — usable from any phone or browser on the local
network, protected by HTTP digest auth (user `admin`, password `web_password` in
`firmware/secrets.yaml`), which keeps the password itself out of the traffic.
Unlike the native API, the web UI is not encrypted, which is why it stays
opt-in.

See [Local control without Home Assistant](docs/local-control.md).

## Home Assistant, Alexa, Google Home, and Matter

Home Assistant consumes the same encrypted native API and remains the
recommended ecosystem seam for dashboards, automations, and voice assistants.
Users who run it can expose the generated entities to Alexa, Google Home, and
Apple Home through the community-maintained
[Home Assistant Matter Hub](https://github.com/RiDDiX/home-assistant-matter-hub),
or through Home Assistant Cloud. See [Voice assistants](docs/voice-assistants.md)
for setup guidance and the rationale for not implementing Matter directly on
the ESP32 in the MVP.

## Command labels

The firmware generator recognizes:

- `fan_off` and `fan_speed_1`, `fan_speed_2`, ...;
- `light_off` and `light_on`;
- `light_brightness_1`, `light_brightness_2`, ...;
- `light_toggle`, `dimmer_down`, and `dimmer_up` for structured relative protocols.

`light_on` plus `light_off` creates a binary light. Contiguous brightness
levels starting at 1 plus `light_off` create a dimmable light. Unknown labels
in a raw-waveform profile create stateless buttons. Relative CJOY light
commands create buttons instead of claiming synchronized light state. Somfy RTS
blind profiles expose `cover_up`, `cover_my` (stop), `cover_down`, and
`cover_prog` (pairing) as buttons.

## Beyond ceiling fans

The `device profile -> firmware` seam is not fan-specific. Each profile carries a
`device_class`, and the first non-fan one is **`roller_blind`**: an experimental
generated adapter for Somfy RTS motors (blinds, roller shutters, awnings) at
433.42 MHz. Somfy is a rolling code, so it cannot be captured and replayed — the
bridge emulates a fresh remote and you pair it with the motor's PROG button:

```sh
uv run ceilingfan learn somfy --remote-id 0x112233 --name "Persiana salon"
```

See [Somfy RTS](docs/protocols/somfy-rts.md) for the full procedure and its
experimental status.

## Status and evidence

This is an early development release. Inspire Pro (Aveiro/Bora/Tavira Pro and
Arteconfort equivalents) is the only identity-based fast onboarding path,
supported by evidence from multiple distinct remotes. CJOY frame generation is
implemented but experimental until replay is validated against its physical
receiver. Nashi, YK8078, and analogous static remotes are learned button by
button into reviewable raw-waveform profiles; their structured family adapters
are still being developed. The wizard contains no commercial-model presets —
it calibrates from the user's own remote.

See the [protocol catalog](docs/protocol-catalog.md), the
[Inspire Pro protocol](docs/inspire-arteconfort-protocol.md), and the
[multi-fan roadmap](docs/multi-fan-protocol-roadmap.md).

## Advanced and diagnostic commands

- `ceilingfan learn listen` streams raw `CFRAW`/`CFLEARN` observations from the
  learning bridge — useful to verify that a remote is being received before or
  instead of running the wizard.
- `ceilingfan learn inspire-pro --remote-id 0x...` and
  `ceilingfan learn cjoy --remote-id 0x...` build profiles directly from an
  already-known remote identity (the wizard normally does this for you).
- `ceilingfan research ...` is the optional RTL-SDR laboratory for protocols
  the bridge does not understand yet. It is never part of normal setup and has
  its own dependencies (`uv sync --extra research` plus the rtl-sdr tools;
  `research doctor` checks both). See
  [Advanced RTL-SDR research](docs/advanced-rtl-research.md).

## Design

The stable interface is:

```text
bridge observation -> device profile -> generated ESPHome firmware
optional research capture -----^
```

Both learning paths produce the same small, reviewable device-profile boundary.
See [Architecture](docs/architecture.md), [CONTEXT.md](CONTEXT.md) for the
domain language, and [AGENTS.md](AGENTS.md) for the AI-agent guide to this
repository.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Do not submit Wi-Fi credentials,
ESPHome secrets, personal network details, or unexplained raw recordings.

## License

MIT
