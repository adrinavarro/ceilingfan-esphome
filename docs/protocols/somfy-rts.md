# Somfy RTS (motorized blinds, roller shutters, awnings)

## Support status

Somfy RTS is the first **non-fan** device class the bridge can drive
(`device_class: roller_blind`). The frame encoder, per-installation rolling-code
counter, firmware transmitter, CLI generator, a native `cover` entity
(open/close/stop), and a pairing button are implemented, and `ceilingfan control
cover` drives it without Home Assistant. It is **experimental** until a generated
transmission is accepted by a physical Somfy motor and confirmed on the air.

This is a *generated* adapter, not learn-and-replay. Somfy RTS is a rolling-code
protocol: the receiver rejects any frame whose 16-bit counter is not ahead of the
last one it accepted, so capturing a press and replaying it does not work. Instead
the bridge **emulates a fresh remote** — a chosen 24-bit address plus its own
rolling counter — and you pair that virtual remote with the motor, exactly as a
Somfy MyLink or a second physical remote would be added.

Nothing is learned by listening, and the learning firmware (433.92 MHz) cannot
even hear Somfy, which transmits at **433.42 MHz**.

## Radio format

The protocol is public (reverse-engineered by Pushstack; reference implementation
in Nickduino's `Somfy_Remote`). One button event is a 7-byte frame:

| Byte | Contents |
|---|---|
| 0 | `0xA7` key (low nibble is a seed) |
| 1 | command nibble (high) + checksum nibble (low) |
| 2–3 | 16-bit rolling code, big-endian |
| 4–6 | 24-bit remote address |

- **Commands**: `my`/stop `0x1`, up `0x2`, down `0x4`, prog `0x8`.
- **Checksum**: XOR of every nibble across the frame, low 4 bits.
- **Obfuscation**: chained XOR, `frame[i] ^= frame[i-1]` for bytes 1–6.
- **Modulation**: 433.42 MHz ASK/OOK, `SYMBOL = 640 µs`, Manchester data bits, a
  wake-up pulse, two (first frame) or seven (repeats) hardware-sync pulses, a
  software sync, and a 30415 µs inter-frame silence.

`src/ceilingfan_esphome/protocols.py` (`somfy_frame_bytes`, `somfy_waveform`)
holds the authoritative encoder; the firmware C++ `build_somfy` lambda mirrors it.

## Procedure

Somfy needs no capture. Retune the radio, generate a profile, deploy, and pair.

1. **Retune the learning/final radio to 433.42 MHz.** The generated firmware sets
   the CC1101 to the profile's frequency automatically, so this matters mainly if
   you also want to watch Somfy traffic with `learn listen` (edit `frequency:` in
   `firmware/learning.yaml`). A CC1101 tuned for the 433 MHz band covers 433.42.

2. **Create a profile with a chosen address.** Pick any unused 24-bit value; it
   identifies *your* virtual remote, not the motor.

   ```sh
   uv run ceilingfan learn somfy --remote-id 0x112233 --name "Persiana salon"
   ```

3. **Deploy** alongside any fan profiles:

   ```sh
   uv run ceilingfan firmware deploy --device ceilingfan-learning.local --web-ui
   ```

   All profiles on one bridge must share a modulation (ASK/OOK — fine), but they
   keep per-profile frequency, so a 433.42 MHz blind and a 433.92 MHz fan coexist.

4. **Pair the virtual remote with the motor.** Put the motor into programming mode
   (hold the PROG button of an already-paired remote until the blind jogs), then
   press the generated **pairing** button within a few seconds. The blind jogs
   again to confirm. Now the cover's open/close/stop control it.

   ```sh
   uv run ceilingfan control button --device home-rf-bridge.local \
     --entity persiana_salon_pairing
   uv run ceilingfan control cover --device home-rf-bridge.local \
     --entity persiana_salon --action open
   ```

   The blind is a native `cover` entity: `--action open|close|stop` from the CLI,
   the open/close/stop widget in the web UI, and a shutter card in Home Assistant.
   It is optimistic (RF is one-way, so there is no real position feedback).

## Verification before trusting it

- With an RTL-SDR, confirm the generated frame matches a real remote on the air at
  433.42 MHz (see [advanced RTL-SDR research](../advanced-rtl-research.md)).
- Confirm the motor still responds after several presses (the rolling counter is
  advancing and being restored across reboots).
- The physical remote and this virtual one keep independent counters; the motor
  accepts both as long as each keeps moving forward, so using the wall remote does
  not desynchronize the bridge.

## Home Assistant

The generated `cover` entity appears directly as a shutter in Home Assistant with
open/close/stop, needing no template helper. Pairing stays a separate button. The
same entity is controllable from the CLI (`ceilingfan control cover`) and the web
UI, so Home Assistant is optional as everywhere else in this project.
