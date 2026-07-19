# Leroy Merlin Inspire Nashi

## Radio format

- 433.92 MHz ASK/OOK;
- marks near 300 or 700 microseconds, with complementary spaces;
- inter-frame gap near 9,050 microseconds;
- up to seven transmissions per button event;
- 33 decoded bits: a 9-bit command followed by a fixed 24-bit remote identity;
- captured remote identity: `0x5FE834`.

No rolling or per-event dynamic field was observed. Every command was captured twice
in different orders and produced the same value.

Only one physical Nashi remote has been studied. Its `0x5FE834` value is evidence for
that remote, not a constant used by the learning implementation.

## Confirmed command map

| Semantic command | 9-bit command |
|---|---:|
| Fan toggle | `000010011` |
| Light toggle | `001011010` |
| Fan speed 1 | `000000100` |
| Fan speed 2 | `000000001` |
| Fan speed 3 | `010100101` |
| Fan speed 4 | `000010000` |
| Fan speed 5 | `001000000` |
| Dimmer down | `000001010` |
| Dimmer up | `010100000` |
| Warm/yellow preset | `010011111` |
| Neutral preset | `011111001` |
| Cool/blue preset | `011110010` |

The full transmitted value is the 9-bit command concatenated with `0x5FE834`.
Repeated fan and light presses kept the same command, so both power buttons are true
relative toggles rather than absolute on/off states.

## ESP32 learning

Until an identity-based structured adapter is supported by evidence from multiple
remotes, learn this remote with the same generic wizard used for any analogous fan:

```sh
uv run ceilingfan learn wizard \
  --name "Nashi bedroom" \
  --output profiles/nashi-bedroom.yaml
```

The wizard discovers the 65-pulse frame shape and approximately 9.05 ms gap from the
first press; those values are not selected through a model preset.

Fan and light toggles, speeds, dimmers, and color-temperature presets are exposed as
stateless buttons because this remote does not provide an absolute fan-off command.
