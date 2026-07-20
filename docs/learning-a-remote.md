# Learning a remote with the bridge

Normal learning uses the assembled ESP32 and CC1101. It does not require an RTL-SDR,
and it never requires the RTL-SDR and ESP32 to occupy two computer USB ports.

## Before learning

1. Assemble and flash the learning firmware as described in the
   [workflow](workflow.md).
2. Identify the remote and fan model. Record label details without personal data.
3. Confirm that the model appears in the [protocol catalog](protocol-catalog.md).
4. Keep a working battery in the remote and place it near the bridge.
5. Do not press the fan receiver's pairing button.

For the current catalog, the learning firmware listens at 433.92 MHz using ASK/OOK.
That shared setting is an observation from the tested fans, not an assumption for
every fan sold.

## The wizard: one command for every supported remote

```sh
uv run ceilingfan learn doctor
uv run ceilingfan learn wizard --name "Bedroom ceiling fan"
```

The wizard opens the bridge's ESPHome log stream and starts with one
identification press: press any button on the remote once, and the observation
decides the learning path. Only the raw path needs buttons named at all. The
profile is written to `profiles/<name-slug>.yaml` (here
`profiles/bedroom-ceiling-fan.yaml`) unless `--output` overrides it, which is
also where the firmware commands look for profiles. The log stream stays quiet
except for RF observations; pass `--verbose` to watch the full ESPHome log.
Users never select a commercial-model preset:

- **Inspire Pro** (Aveiro Pro, Bora Pro, Tavira Pro, and equivalent Arteconfort
  models): the identification press reveals the remote's static 25-bit identity.
  The family adapter combines that identity with the verified 8-bit command map and
  generates fan off, six absolute speeds, light off, and eight absolute brightness
  levels. No buttons need naming and no further presses are required.
- **CJOY**: the identification press reveals the 32-bit identity and selects the
  experimental four-phase adapter, which generates the decoded checksum at runtime.
  After deployment, use the generated synchronization button before physical
  validation; it sends only the absolute fan-off command. See
  [CJOY four-phase protocol](protocols/cjoy-dynamic.md).
- **Any other static repeated ASK/OOK remote** (including Nashi and YK8078): the
  identification press calibrates frequency, frame length, and frame gap from that
  remote, then the wizard asks for labels such as `fan_toggle`, `fan_speed_1`, or
  `light_toggle` and warns immediately if the label set will not produce a fan or
  light entity. Later presses must match the session fingerprint, which rejects
  unrelated RF traffic without importing any model-specific identity or payload.

One observation already contains at least two repeated copies of the frame; use
`--attempts 2` when a command is known to emit the same waveform on every press. Do
not use multiple attempts for a remote button that deliberately alternates two
absolute states unless each state is learned under its own label.

The learner writes `<profile>.observations.yaml` beside the profile. This evidence
contains median-ready durations rather than large I/Q samples and should be kept for
review and troubleshooting. If the session is interrupted, rerun the same command
with `--resume`; completed labels are skipped. A complete evidence file can also
rebuild its profile without reconnecting to the bridge.

For a scripted session, provide the controls explicitly:

```sh
uv run ceilingfan learn wizard \
  --name "Other ceiling fan" \
  --command fan_toggle \
  --command fan_speed_1 \
  --command fan_speed_2 \
  --command light_toggle
```

The raw path requires 433.92 MHz ASK/OOK, a clear frame gap, at least two repeated
frames per button event, and a stable waveform for each learned label. It cannot
safely learn rolling codes, encrypted frames, changing counters/checksums, FSK, or
2.4 GHz remotes. The repetition requirement is the learner's anti-noise evidence,
so remotes that transmit each button event only once — some doorbells and blind
remotes behave this way — are also rejected: the wizard times out instead of
building an uncertain profile. Holding the button usually produces the repeated
frames the fan remotes in the catalog emit naturally.

## Multiple identical fans

Each physical remote has its own identity, so learn and name each installation
separately:

```text
Bedroom remote -> bedroom identity -> profiles/bedroom.yaml
Office remote  -> office identity  -> profiles/office.yaml
```

Never copy one identity to another room. The known household Inspire Pro evidence
contains three recovered identities; a fourth installation still needs its own
bridge observation before it can be deployed safely.

The quick identity-only workflow is limited to Inspire Pro because multiple remotes
show which bits vary per installation while the family command map remains stable.
An identity seen in only one Nashi or YK8078 capture is evidence, not a family
constant, and is never embedded in the wizard.

## Diagnostics and advanced identity commands

`learn listen` streams the same observations the wizard consumes, without creating
anything. Use it to confirm that a remote is being received at all:

```sh
uv run ceilingfan learn listen --device ceilingfan-learning.local
```

Press one unambiguous normal button two or three times. A valid repeated frame
produces a line like:

```text
CFLEARN family=inspire_pro command=0xE2 remote_id=0x05A243E matches=7
CFLEARN family=cjoy command=0x1F remote_id=0x175D0310 phase=2 matches=5
CFRAW frequency=433920000 repetitions=6 gap=9000 preamble=none frame=...
```

Repeat the same button and verify that `remote_id` remains identical. If possible,
press a second command and confirm the same identity with a different command byte.
The bridge ignores unrecognized command bytes and does not modify the fan's pairing.

When an identity is already known — from a previous listen session or a recorded
evidence file — a structured profile can be created directly, skipping the wizard:

```sh
uv run ceilingfan learn inspire-pro \
  --remote-id 0x05A243E \
  --name "Bedroom ceiling fan"

uv run ceilingfan learn cjoy \
  --remote-id 0x175D0310 \
  --name "CJOY bedroom"
```

When adding a remote outside the supported constraints, contributors may choose the
separate [advanced RTL-SDR research](advanced-rtl-research.md) track. That equipment
is useful for protocol development, but it does not become a requirement for users
after a family decoder is incorporated.

## Validation and failure modes

After OTA deployment, test every generated action against the intended fan and check
that no other fan reacts. `ceilingfan firmware validate --device <bridge>` walks
through every command, sends it, and records what physically happened. Stop and
investigate if:

- repeated presses report different identities or frame lengths;
- a field changes on every press;
- commands work only intermittently;
- another installation responds;
- the receiver stops accepting a previously valid command.

These can indicate noise, incorrect receiver settings, stateful commands, counters,
checksums, or rolling codes. Do not turn uncertain evidence into a supported profile.
