# Inspire Pro and Arteconfort protocol family

## Known compatible remotes

The protocol documented here has been observed on factory remotes supplied with
the following ceiling fans:

- Leroy Merlin Inspire Aveiro Pro
- Leroy Merlin Inspire Bora Pro
- Leroy Merlin Inspire Tavira Pro
- Arteconfort-branded equivalents of these models

Manufacturers can change radio modules between hardware revisions without changing
a product name. Treat this as a verified protocol family, not a guarantee for every
past or future revision. Confirm the frequency and capture at least one command
before transmitting.

## Evidence

The household inventory contains four remotes from this family. Three independent
remote identities have been decoded and compared so far. They use the same command byte and
timings, but each remote transmits a different static 25-bit identifier:

| Remote | Identifier as transmitted | 25-bit value |
|---|---|---|
| A | `00 77 6D` + `0` | `0x000EEDA` |
| B | `2D 12 1F` + `0` | `0x05A243E` |
| C | `40 76 B0` + `1` | `0x080ED61` |

The fourth household unit still needs its identity captured before deployment; do not
reuse one of the three values above for it.

The final bit is part of the identifier. It is not a fixed frame terminator: remotes
A and B end in zero, while remote C ends in one.

No pairing button was pressed during this research. The stable identifier across
normal commands strongly suggests that pairing makes the fan receiver remember a
remote's 25-bit identifier. The exact pairing transmission and receiver behavior
remain unverified.

## Radio and frame format

The tested remotes use:

- center frequency: 433.92 MHz;
- modulation: ASK/OOK;
- seven repetitions per button event;
- 33 data bits per repetition;
- payload: an 8-bit command followed by a static 25-bit remote identifier;
- inter-frame gap: approximately 7,688 microseconds.

Bits are pulse-width encoded. The measured nominal timings are:

| Bit | Mark | Space |
|---|---:|---:|
| `0` | 1,053 us | 337 us |
| `1` | 355 us | 1,031 us |

These measurements are specific to this protocol family. Neither 433.92 MHz nor
these timings should be assumed for an unknown ceiling fan remote.

## Command map

Fan speed and light brightness are absolute values maintained by the remote. The
minimum brightness command is transmitted again when the user tries to dim below
level 1.

| Command | Byte |
|---|---:|
| Fan off | `E2` |
| Fan speed 1 | `F5` |
| Fan speed 2 | `ED` |
| Fan speed 3 | `E5` |
| Fan speed 4 | `DD` |
| Fan speed 5 | `D5` |
| Fan speed 6 | `CD` |
| Light off | `DB` |
| Light brightness 8 | `C4` |
| Light brightness 7 | `CC` |
| Light brightness 6 | `D4` |
| Light brightness 5 | `DC` |
| Light brightness 4 | `E4` |
| Light brightness 3 | `EC` |
| Light brightness 2 | `F4` |
| Light brightness 1 | `FC` |

Label the learned brightness waveforms `light_brightness_1` through
`light_brightness_8`. Together with `light_off`, the generator exposes them as one
dimmable Home Assistant light entity. It disables transitions so a single Home
Assistant brightness change produces one absolute RF command.

For example, fan speed 2 from remote C is transmitted as:

```text
ED 40 76 B0 1
^^ \________/
|       |
|       +-- static 25-bit remote identifier
+---------- 8-bit command
```

## Multiple fans on one bridge

Every physical remote needs its own learned profile because its 25-bit identifier is
different. Supply all profiles to the same firmware build to control several fans
with one ESP32 and CC1101:

```sh
uv run ceilingfan firmware build \
  --profile profiles/bedroom.yaml \
  --profile profiles/office.yaml \
  --bridge-name "Home RF bridge"
```

The bridge exposes separate Home Assistant entities for each profile and serializes
their transmissions through the shared CC1101. Do not merge captures from two
remotes into one profile, even when both fans are the same model.
