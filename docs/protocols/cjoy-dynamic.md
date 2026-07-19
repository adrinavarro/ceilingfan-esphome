# CJOY four-phase protocol

## Support status

The encoder, ESP32+CC1101 learning decoder, profile generator, per-installation
phase state, and Home Assistant entities are implemented. The implementation is
still marked **experimental** until a generated transmission is accepted by the
physical fan receiver.

An RTL-SDR is not required to learn another CJOY installation now that the protocol
family is decoded. The learning bridge can report its 32-bit remote identity.

## Evidence

The local evidence contains 78 clean frames across 16 button events. Every event
repeats one identical frame five times. Repeated commands, two ordered light
sequences, consecutive fan-off events, and the captured chronological order expose
three complete cycles of the phase field.

`fan_speed_3-01` contains interference rather than a decodable remote event;
`fan_speed_3-02` is the clean replacement. Apparent jumps early in the sequence agree
with button events that occurred outside a clean capture.

## Radio format

- 433.92 MHz ASK/OOK;
- one wake-up pair near `+8805, -2860` microseconds;
- five repeated frames per button event;
- each frame starts near `+7394, -1083` microseconds;
- bit 0 is near `+348, -721` microseconds;
- bit 1 is near `+742, -329` microseconds;
- 49 data bits per frame.

The frame structure is:

```text
[32-bit remote identity] [6-bit command] [9-bit phase code] [10]
```

The captured remote identity is:

```text
00010111010111010000001100010000  (0x175D0310)
```

## Command field

| Semantic command | 6-bit command | Hex |
|---|---:|---:|
| Fan off | `011111` | `0x1F` |
| Fan speed 1 | `101011` | `0x2B` |
| Fan speed 2 | `010000` | `0x10` |
| Fan speed 3 | `001000` | `0x08` |
| Fan speed 4 | `101111` | `0x2F` |
| Fan speed 5 | `100011` | `0x23` |
| Fan speed 6 | `000100` | `0x04` |
| Light toggle | `100000` | `0x20` |
| Dimmer down | `011001` | `0x19` |
| Dimmer up | `100001` | `0x21` |

## Phase/checksum encoder

The former “11-bit dynamic field” is a two-bit phase encoded with a
command-dependent checksum, followed by the constant bits `10`. The phase advances
`0 -> 1 -> 2 -> 3 -> 0` once per button event, not once per repeated frame.

```python
fold = [0xCE, 0x0D, 0x95, 0x67]
high = 1 if phase < 2 else 0
phase_code = (high << 8) | ((((command << 1) | high) ^ fold[phase]) & 0xFF)
tail = (phase_code << 2) | 0b10
```

This formula reproduces every observed suffix exactly. For example, the four valid
fan-off suffixes are:

| Phase | 11-bit suffix |
|---:|---:|
| 0 | `0x7C6` |
| 1 | `0x4CA` |
| 2 | `0x2AE` |
| 3 | `0x166` |

## Firmware behavior

Each CJOY device profile stores its own 32-bit identity and restored two-bit phase.
The runtime adapter constructs the waveform, transmits five identical frames, then
advances that profile's phase. Multiple CJOY fans on one RF bridge therefore do not
share phase state.

Home Assistant receives:

- one six-speed fan entity with absolute off and speed commands;
- light toggle, dimmer down, and dimmer up buttons because those commands are
  relative;
- a `synchronize RF phase` button.

Synchronization queues fan-off at phases 0, 1, 2, and 3 and finishes with the local
next phase set to 0. Fan off is deliberately used because repeating an absolute off
command is safe. Never use this strategy for toggle or dimmer commands.

The synchronization behavior covers the conservative case where the receiver
expects the next phase and a physical remote has moved it. Physical validation must
still determine whether the receiver enforces ordering or merely uses phase to
deduplicate repeated frames.

## Profile creation

After the learning bridge reports a CJOY identity:

```sh
uv run ceilingfan learn cjoy \
  --remote-id 0x175D0310 \
  --name "CJOY bedroom" \
  --output profiles/cjoy-bedroom.yaml
```

The resulting schema-version-2 profile contains protocol family, remote identity,
and semantic command codes instead of frozen raw waveforms.
