# Multi-fan and multi-protocol roadmap

## Target household scenario

One ESP32 and one 433 MHz CC1101 should expose several independently named Home
Assistant devices, including four identical Inspire Pro installations in different
rooms and additional YK8078 and Nashi fans. A command for one room must never be sent
with another room's remote identity.

All currently captured families use 433.92 MHz ASK/OOK, so one correctly matched
433 MHz CC1101 module and antenna can cover the known household fleet. The architecture
must still retain per-profile radio settings for future families.

## Model boundaries

```text
RF bridge (one ESP32 + CC1101)
  -> device profile: Bedroom Inspire Pro
       -> Inspire Pro protocol adapter
       -> bedroom remote identity
  -> device profile: Office Inspire Pro
       -> Inspire Pro protocol adapter
       -> office remote identity
  -> device profile: Small-room YK8078
       -> YK8078 protocol adapter or raw waveforms
  -> device profile: Nashi
       -> Nashi protocol adapter or raw waveforms
  -> device profile: CJOY
       -> CJOY four-phase protocol adapter
       -> independent restored phase
```

A protocol family is reusable knowledge. A device profile is a physical fan
installation. Four identical Inspire Pro fans therefore share one adapter but require
four profiles and four remote identities.

## Capability semantics

Home Assistant entities must reflect what RF can actually guarantee:

| RF capability | Home Assistant direction |
|---|---|
| Absolute fan speeds | Normal multi-speed fan entity |
| Absolute light on/off | Normal light entity |
| Absolute brightness levels | Dimmable light with discrete mapped levels |
| Relative fan or light toggle | Optimistic entity or explicit button; document desynchronization risk |
| Relative dimmer up/down | Buttons/actions until reliable state tracking exists |
| Color-temperature presets | Three preset actions or a discretized color-temperature entity |
| Generated phase/checksum | Stateful adapter plus explicit synchronization |
| Unknown dynamic/rolling command | Unsupported until generation and receiver acceptance are proven |

Physical remotes can change receiver state without informing Home Assistant. Absolute
commands recover synchronization on every action; relative toggles cannot.

## Implementation sequence

### 1. Finish the multi-profile bridge foundation

- accept repeated `--profile` arguments for build, deploy, doctor, and validation;
- create distinct fan/light entity IDs from profile names;
- serialize every transmission through one queued radio script;
- apply the selected profile's frequency and power immediately before transmission;
- reject duplicate normalized profile identifiers.

This work already exists in the current working tree and has automated coverage.

### 2. Evolve the profile schema

Add explicit fields for:

- device class distinguishing future non-fan installations (implemented:
  `device_class`, with `ceiling_fan` as the only class so far);
- protocol family/adapter identifier;
- remote identity and its bit width;
- command semantics: absolute, relative, or dynamic;
- capability mappings for speed, brightness, color temperature, and buttons;
- raw waveform fallback for protocols without a structured encoder.

Schema migration must keep existing schema-version-1 waveform profiles loadable.

### 3. Implement adapters in evidence order

1. **Inspire Pro — first slice implemented**: the learning firmware recognizes repeated frames
   and reports the 8-bit command plus 25-bit identity. The profile generator creates
   the complete verified command set from that identity. Physical four-installation
   isolation remains a release gate.
2. **Generic raw waveform — ESP32 learning implemented**: learn Nashi, YK8078,
   and analogous repeated static ASK/OOK commands without RTL-SDR; preserve compact
   evidence and expose relative/unknown semantics as stateless buttons.
3. **Inspire Nashi structured adapter**: generate a 9-bit command plus 24-bit
   identity so future installations need only one observation.
4. **Inspire YK8078 structured adapter**: encode the confirmed static values after
   resolving framing and on/off/color assignments.
5. **CJOY four-phase — encoder implemented**: generate its command-dependent
   phase/checksum, keep phase per profile, expose relative light controls as buttons,
   and provide safe fan-off synchronization. Keep the adapter experimental until the
   physical receiver accepts generated frames and phase recovery is validated.

Bridge-based reception is the default acquisition interface for every supported
adapter. RTL-SDR captures remain an optional protocol-research fallback and must not
become an end-user dependency.

### 4. Validate physical isolation

The release gate for the four Inspire Pro installations is:

- four separately named Home Assistant fan/light pairs;
- four different remote identities;
- every speed, off, light, and brightness command tested against its intended fan;
- no other fan responds during each validation;
- rapid commands to different rooms remain ordered and are not merged;
- OTA updates preserve all profiles and entity identities.

### 5. Validate mixed-family operation

Build one bridge containing at least one Inspire Pro, one YK8078, one Nashi, and one
CJOY profile. Verify radio retuning/settings, entity semantics, queued transmission,
per-profile CJOY phase, synchronization after physical-remote use, and recovery after
an unavailable fan. CJOY remains experimental until those receiver tests pass.
