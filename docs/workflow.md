# Three-phase workflow

The workflow never requires the RTL-SDR and ESP32 to be connected to the computer at
the same time. Each phase ends by producing a durable handoff for the next phase.

## Phase 1: Learn

**Connected to the computer:** RTL-SDR only.

**Other equipment:** original remote and ceiling fan.

```text
Spectrum scan -> labeled I/Q captures -> device-profile.yaml
```

The frequency should be discovered before selecting a band-specific CC1101 module
and antenna. The ESP32 is not used for this phase.

The durable handoff is `device-profile.yaml`. Raw captures may be archived locally,
but they are not needed for normal operation after a stable profile is produced.

## Phase 2: Hardware

**Connected to the computer:** assembled ESP32 + CC1101 over one USB cable.

**Not connected:** RTL-SDR.

```text
Physical assembly -> USB onboarding flash -> Wi-Fi + OTA endpoint
```

The onboarding firmware does not depend on learned commands. It establishes
encrypted networking, OTA recovery, logging, and CC1101 SPI communication.

The durable handoff is a powered device reachable as
`ceilingfan-onboarding.local` or by its IP address. After onboarding, unplug it from
the computer and use an independent USB power supply.

## Phase 3: Firmware

**Connected to the computer:** nothing over USB.

**Powered on the local network:** onboarded ESP32 + CC1101.

```text
device-profile.yaml -> generated ESPHome firmware -> OTA -> physical validation
```

The final firmware is normally deployed over OTA. USB remains a recovery path if
networking or OTA is broken, but it is not part of the normal deployment phase.

## Resource matrix

| Requirement | Learn | Hardware | Firmware |
|---|---:|---:|---:|
| RTL-SDR USB connection | Yes | No | No |
| ESP32 USB connection | No | Yes | No |
| ESP32 Wi-Fi connection | No | Established | Yes |
| Original remote | Yes | No | Validation only |
| `rtl_power` / `rtl_sdr` | Yes | No | No |
| ESPHome | No | Yes | Yes |

