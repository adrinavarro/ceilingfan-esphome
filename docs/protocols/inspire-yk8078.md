# Leroy Merlin Inspire YK8078

## Remote identification

| Field | Value |
|---|---|
| Remote model | `YK8078` |
| Hardware/revision | `A02028-8` |
| PCB | `36YFT-4840S` |
| Manufacturing date | `2022-01` |
| Region/firmware markings | `RCNASHIEU`, `RCSHAMALEU` |

The remote came with a smaller-diameter Leroy Merlin Inspire ceiling fan. The exact
retail fan model still needs to be recorded.

## Radio format

- 433.92 MHz ASK/OOK;
- marks near 300 or 900 microseconds, with complementary spaces;
- inter-frame gap near 4,360 microseconds;
- seven transmissions per button event, normally six fully decoded after detector
  startup;
- stable prefix `0x396E` in every observed frame;
- no rolling or per-event dynamic field observed.

Only one physical YK8078 remote has been studied. The `0x396E` prefix remains capture
evidence and is not embedded in the learning implementation.

The capture tooling currently displays the frame as 33 observed mark decisions. The
values below use the stable hexadecimal representation produced during analysis; a
structured adapter must confirm whether one observed edge is a framing symbol before
freezing a bit-field schema.

## Confirmed command map

| Semantic command | Observed value |
|---|---:|
| Fan toggle | `0x396E8000` |
| Light state A | `0x396E2004` |
| Light state B | `0x396E2006` |
| Fan speed 1 | `0x396E4200` |
| Fan speed 2 | `0x396E4400` |
| Fan speed 3 | `0x396E4600` |
| Fan speed 4 | `0x396E4800` |
| Fan speed 5 | `0x396E4A00` |
| Fan speed 6 | `0x396E4C00` |
| Dimmer down | `0x396E3014` |
| Dimmer up | `0x396E3016` |
| Color-temperature preset A | `0x396E2012` |
| Color-temperature preset B | `0x396E2014` |
| Color-temperature preset C | `0x396E2016` |

Three repeated fan-toggle presses all produced `0x396E8000`, so fan power is a true
relative toggle. Four repeated light-button presses alternated exactly between
`0x396E2004` and `0x396E2006`, proving that the remote maintains two absolute light
states. Which value means on remains unknown because the fan receiver was unpowered.

The remote has three dedicated color-temperature buttons. The three values are
confirmed, but their assignment to warm/yellow, neutral, and cool/blue was not recorded
unambiguously in the original prompts and must be physically validated.

## ESP32 learning

Learn every control with the same generic wizard used for any analogous fan:

```sh
uv run ceilingfan learn wizard \
  --name "Small-room fan" \
  --output profiles/small-room.yaml
```

During label entry, call the alternating light values `light_state_a` and
`light_state_b` unless their physical on/off meaning is known. Unknown color controls
can similarly use `color_temperature_a` through `_c`. They become stateless Home
Assistant buttons.

The wizard discovers the 65-pulse frame shape and approximately 4.36 ms gap from the
first press, while the complete payload comes from the user's own remote.
