# Architecture

The normal system has one radio bridge and a file-backed profile boundary:

```text
original remote
      |
      v
CC1101 receiver -> family adapter / static learner -> device profile -> ESPHome generator
      ^                                                        |
      |                                                        v
ESP32 learning bridge <------------------------------ multi-fan RF bridge
```

An optional research adapter reaches the same boundary without contaminating the
normal setup interface:

```text
RTL-SDR raw I/Q -> deterministic waveform learner -> device profile
  optional advanced research only
```

The firmware generator does not need to know whether a profile came from a structured
bridge observation or an optional research capture.

## Learning interface

The learning firmware configures the CC1101 as a receiver and ESPHome streams its
observations over Wi-Fi. A protocol-family adapter recognizes a validated frame and
extracts the smallest installation-specific value needed to generate commands.

The Inspire Pro adapter recognizes repeated 33-bit frames, reports their 8-bit
command and static 25-bit remote identity, and uses that identity with the verified
family command map to synthesize a complete static profile. The CJOY adapter
recognizes repeated 49-bit frames, validates their four-phase checksum, and creates a
structured profile whose waveform is generated at runtime. Protocol knowledge is
reusable; a profile remains specific to one physical fan.

Nashi and YK8078 currently use a second adapter at the same learning seam:

```text
repeated raw observation -> median static waveform -> DeviceProfile
```

The learning firmware emits a compact `CFRAW` observation containing a canonical
frame, gap, optional short preamble, and repetition count. The host learner labels
and combines those observations. The first observation calibrates a session-local
frequency, frame-length, and gap fingerprint; neither model names nor payload bits
from household examples participate. The resulting raw profile crosses the same
`DeviceProfile -> firmware` seam as a structured family profile; the generator does
not know which learning adapter produced it.

Identity-only fast onboarding requires comparison across multiple physical remotes.
Inspire Pro satisfies that evidence threshold. CJOY's structured, stateful adapter is
an experimental exception because a raw static waveform cannot represent its
four-phase field; it still learns the complete 32-bit value from the current remote.
Both adapters are selected by observations inside the generic wizard rather than by
a user-facing model preset.

An adapter must fail clearly if evidence is dynamic, ambiguous, or outside its known
constraints. CJOY remains experimental because physical receiver replay is pending,
but its previously changing field is now generated deterministically.

## Optional research interface

The `research` commands delegate spectrum scanning and raw capture to `rtl_power`
and `rtl_sdr`. Captures store SigMF metadata beside samples so center frequency,
sample rate, datatype, gain, and semantic label remain attached.

The deterministic waveform learner demodulates ASK/OOK amplitude, removes short
glitches, finds inter-frame gaps, groups repeated frames, and takes median timings.
Its raw-waveform profile is an escape hatch for static protocols that do not yet have
a structured encoder.

This interface exists for protocol contributors. No component in normal setup,
bridge learning, OTA deployment, or installed operation depends on RTL hardware or
tools.

## Firmware interface

The firmware module accepts one profile per physical installation, maps semantic
commands to transmitted waveforms, and exposes only confirmed capabilities. One
ESPHome bridge creates separate fan/light entities for every profile. All commands
use one queued transmitter; immediately before each command, it applies that
profile's frequency and output power.

Profile names are the entity identity boundary. Their normalized identifiers must
be unique so Home Assistant and voice assistants never receive ambiguous entities.
Adding a profile regenerates and deploys firmware over OTA because ESPHome entities
are compiled into the device.

Schema-version-1 profiles retain captured raw waveforms. Schema-version-2 profiles
name a structured protocol family, remote identity, and semantic command codes. Both
cross the same `DeviceProfile -> firmware` seam; callers do not handle protocol
timings or state. CJOY phase is stored independently for every profile and relative
commands are exposed as buttons instead of false absolute state.

The domain boundary is recorded in [CONTEXT.md](../CONTEXT.md). The decision to host
many independent profiles on one serialized RF bridge is in
[ADR 0001](adr/0001-one-bridge-many-device-profiles.md). See the
[multi-fan roadmap](multi-fan-protocol-roadmap.md) for adapter sequencing.

## Control, automation, and voice seams

Generated ESPHome entities are the installed control boundary. Both direct local
control and Home Assistant use the encrypted native API, while RF timings and radio
serialization remain private to the firmware module:

```text
local CLI or agent --------------------+
phone browser (optional web UI) -------+
                                       v
RF bridge <- generated ESPHome entities/native API <- Home Assistant <- ecosystems
```

The CLI intentionally commands entity IDs rather than RF profile internals. This
keeps one capability and validation model for humans, agents, and Home Assistant.
The optional `--web-ui` surface is ESPHome's own web server over the same generated
entities, protected by basic auth and off by default; it adds phone/browser control
without Home Assistant but never bypasses the entity boundary. Home Assistant owns richer
automation, dashboards, state reconciliation, and ecosystem exposure, but it is not
required for basic local operation. See [Local control](local-control.md) and
[Voice assistants](voice-assistants.md).

A future direct-Matter adapter could consume the same profiles without changing
learning.

## Unsupported protocols

A protocol that changes valid frames over time needs a protocol-specific adapter,
not another special case in the static waveform learner. The system must fail with
evidence when it cannot produce a safe, stable command.
