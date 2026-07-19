# Four-stage normal workflow

The ESP32 and CC1101 are both the learning instrument and the installed RF bridge.
An RTL-SDR is not used anywhere in this normal workflow.

## Stage 1: Assemble and onboard

**Connected to the computer:** assembled ESP32 + CC1101 over one USB cable.

```text
physical assembly -> USB onboarding flash -> Wi-Fi + OTA learning bridge
```

The first flash stores Wi-Fi credentials, enables encrypted ESPHome API access and
OTA, verifies CC1101 SPI communication, and starts a 433.92 MHz ASK/OOK receiver for
the currently supported protocol catalog.

The durable handoff is a bridge reachable as `ceilingfan-learning.local` or by its
IP address. After onboarding, it can be unplugged from the computer and powered by
an ordinary USB supply.

## Stage 2: Learn

**Powered:** onboarded ESP32 + CC1101 and the original remote.

**Connection:** Wi-Fi for ESPHome logs. The USB cable may supply power, but no serial
connection is required.

```text
remote button -> CC1101 observation -> family adapter or static learner -> device profile
```

Run `ceilingfan learn wizard` once per fan with that fan's own remote. The wizard
starts with one identification press and recognizes known protocol families from
it: an Inspire Pro observation reveals the remote's static 25-bit identity and the
verified family encoder creates all fan and light commands without naming or
recording any button; a CJOY observation selects its experimental stateful
adapter. Any other static remote is learned button by button — the wizard asks for
command labels only in that case, warning up front when a label set will not
produce a fan or light entity. The bridge splits each button event into repeated
frames, rejects events without at least two repeated frames, takes median timings,
and stores both observation evidence and a raw-waveform profile. Relative or
semantically unknown actions become stateless ESPHome buttons. Dynamic frames,
unsupported modulation, and ambiguous captures still fail instead of producing a
misleading profile.

Each physical installation receives a separate profile. Four identical fans share
one protocol family but still need four remote identities and four profiles. Learning
normal command traffic is passive and does not require touching the receiver's
pairing button. Profiles default into `profiles/` (one `<name-slug>.yaml` per
fan); later firmware commands pick them up automatically.

`ceilingfan learn listen` is the diagnostic view of the same log stream, useful to
confirm that a remote is being received at all.

## Stage 3: Generate, deploy, and validate

**Powered on the local network:** onboarded ESP32 + CC1101.

**Connected to the computer over USB:** nothing.

```text
one or more device profiles -> generated ESPHome firmware -> OTA -> physical validation
```

`ceilingfan firmware build` and `deploy` use every profile in `profiles/` when no
explicit `--profile` options are given, and print the list they found. All exposed
fan installations share a serialized CC1101 transmitter but keep distinct names,
identities, and radio settings. Adding a profile currently requires firmware
regeneration and OTA because ESPHome entities are compile-time definitions.

The deploy ends by printing the bridge's final hostname. Then
`ceilingfan firmware validate --device <that hostname>` sends every generated
command in turn and records whether the intended fan physically reacted.

Pass `--web-ui` to also serve a phone/browser control page from the bridge itself
(HTTP digest auth; see [Local control](local-control.md) for the trade-off).

Keep the learning firmware installed until every currently available remote has its
own profile, then run one final deployment. For a worked example, including four
identical installations plus a different fifth fan, see
[One bridge for a multi-fan home](multi-fan-home.md).

## Stage 4: Operate locally

**Powered:** final ESP32 + CC1101 bridge on the local network.

**Home Assistant:** optional.

```text
CLI or local agent -> encrypted ESPHome API -> generated entity -> serialized RF transmit
phone browser -----> optional bridge web UI -^
```

Run `ceilingfan control list --device <final-hostname>` to discover stable entity
identifiers (`control discover` finds the hostname itself over mDNS, and
`CEILINGFAN_DEVICE` makes `--device` optional). Fan, light, and stateless button
commands then use those identifiers. A bridge deployed with `--web-ui` also serves
its own control page for phones and browsers. See
[Local control without Home Assistant](local-control.md).

Home Assistant connects through the same native API when automation dashboards or
voice-assistant exposure are wanted. It is not a prerequisite for direct local
operation.

## Adding a fan after final deployment

The final firmware transmits but does not run the learning receiver. Put the bridge
back into learning mode temporarily, entirely over OTA:

```sh
uv run ceilingfan learn prepare --device home-rf-bridge.local
uv run ceilingfan learn wizard \
  --device ceilingfan-learning.local \
  --name "Guest room fan"
```

Then run `ceilingfan firmware deploy` again; it picks up every profile in
`profiles/`, old and new. Normal control is unavailable only while the learning
firmware is running. USB is a recovery path, not part of this expansion flow.

USB remains a recovery path if Wi-Fi or OTA is broken. It is not part of routine
learning or deployment.

## Resource matrix

| Requirement | Onboard | Learn | Deploy | Operate |
|---|---:|---:|---:|---:|
| ESP32 + CC1101 | Yes | Yes | Yes | Yes |
| ESP32 USB data connection | Yes | No | No | No |
| ESP32 Wi-Fi connection | Established | Yes | Yes | Yes |
| Original remote | No | Yes | Validation only | No |
| ESPHome tooling | Yes | Yes | Yes | No |
| Home Assistant | No | No | No | No |
| RTL-SDR or RTL tools | **No** | **No** | **No** | **No** |

## Separate optional research track

Protocol contributors may use an RTL-SDR before or alongside this workflow to study
an unsupported frequency, modulation, or frame structure. That work lives under
`ceilingfan research`, produces optional SigMF evidence, and eventually implements
a bridge decoder or a safe profile adapter. It is not a fourth setup stage and is
not required by end users. See [Advanced RTL-SDR research](advanced-rtl-research.md).
