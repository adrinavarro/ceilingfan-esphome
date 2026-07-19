# Architecture

`ceilingfan-esphome` has three deep modules with file-backed interfaces:

```text
RTL-SDR capture      Deterministic learner        ESPHome generator
       |                      |                           |
       v                      v                           v
 .sigmf-data/meta  ->  device-profile.yaml  ->  ceiling-fan.yaml
```

These are also three operational phases. The capture module uses only an RTL-SDR,
hardware onboarding uses only an ESP32 over USB, and final firmware deployment uses
OTA over the local network. No shared USB session exists between the phases.

## Capture module

The capture module delegates radio access to `rtl_power` and `rtl_sdr`. It always
writes SigMF metadata beside raw samples so sample rate, center frequency, datatype,
gain, and semantic label cannot be separated from the recording.

## Learning module

The learning module currently demodulates ASK/OOK amplitude, removes short glitches,
finds long inter-frame gaps, groups repeated frames, and takes median timings across
observations. It returns a waveform profile rather than requiring a speculative bit
decoder.

This supports static remotes even when the meaning of every bit is unknown. It also
makes uncertainty explicit through confidence and observation counts.

## Firmware module

The firmware module maps semantic command labels to learned waveforms and exposes
only confirmed capabilities. ESPHome owns networking, encrypted Home Assistant
integration, OTA updates, SPI, and CC1101 mode switching.

## Automation and voice seam

The MVP ends its device-specific responsibilities at Home Assistant entities. Voice
ecosystems sit behind a separate adapter:

```text
RF bridge -> ESPHome -> Home Assistant -> Matter Hub or HA Cloud -> voice assistant
```

This concentrates RF learning and transmission in `ceilingfan-esphome`, while Home
Assistant owns entity state and ecosystem exposure. A future direct-Matter firmware
adapter can consume the same `device-profile.yaml` without changing the capture or
learning modules. See [Voice assistants](voice-assistants.md) for the decision and
trade-offs.

## Unsupported protocols

A protocol that changes valid frames over time needs a new adapter, not another
special case in the waveform learner. The program must fail with evidence when it
cannot produce a stable waveform.
