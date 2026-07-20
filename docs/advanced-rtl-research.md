# Advanced RTL-SDR protocol research

This is an optional contributor workflow for unsupported radio protocols. An
RTL-SDR is **not required** to assemble the bridge, learn a supported fan, generate
firmware, deploy over OTA, or operate the finished device.

## When this laboratory is useful

Use an RTL2832U-based receiver when one or more of these are true:

- the remote's frequency is unknown and cannot be established from its labels or
  documentation;
- its modulation is unknown or is not the catalog's known ASK/OOK setting;
- the CC1101 receiver does not produce a clean observation with candidate settings;
- raw I/Q evidence is needed to distinguish framing, checksums, counters, or FSK;
- a changing field requires repeated, offline comparison.

Once a family is understood and a bridge decoder exists, ordinary users should use
the ESP32+CC1101 learning path instead.

## Equipment

- a basic RTL2832U RTL-SDR receiver;
- an antenna that covers the candidate band;
- the original remote with a working battery.

The RTL-SDR and ESP32 do not need to be attached to the computer together. Research
can occur before the bridge is assembled, and its durable output is a documented
protocol adapter or a reviewable static waveform profile.

## Discover a frequency

Install the research dependencies and check the optional tools. The research
track has its own Python extra (numpy) so that normal setups never carry it:

```sh
uv sync --extra research
uv run ceilingfan research doctor
```

Then scan while pressing a button repeatedly:

```sh
uv run ceilingfan research scan --start 420M --end 450M --duration 30s
```

Inspect `captures/scan.csv` for the strongest repeatable peak. Do not infer that
every ceiling fan uses 433.92 MHz merely because the current catalog does.

## Make controlled captures

Capture one semantic command at a time, with at least three independent attempts:

```sh
uv run ceilingfan research capture fan_off \
  --frequency 433.92M --attempt 1 --directory captures/research-remote
uv run ceilingfan research capture fan_off \
  --frequency 433.92M --attempt 2 --directory captures/research-remote
uv run ceilingfan research capture fan_off \
  --frequency 433.92M --attempt 3 --directory captures/research-remote
```

During each four-second recording, press only the named button several times and
release it fully between presses. Keep antenna geometry stable. Record state-changing
or wake-up presses separately, and never mix recordings from different remotes in
one directory.

Absolute commands are easier to expose safely than relative toggles or increments.
Do not press a pairing button unless pairing behavior is explicitly in scope and the
risk to the existing installation is accepted.

## Analyze a static ASK/OOK remote

```sh
uv run ceilingfan research analyze \
  --captures captures/research-remote \
  --name "Research remote"
```

The profile lands in `profiles/<name-slug>.yaml` — the same place the wizard
writes and `firmware deploy` looks — unless `--output` overrides it.

The generic learner can retain stable raw waveforms without fully decoding their
bits. Low confidence, inconsistent lengths, or fields that change on every press
must be investigated rather than published as safe replay support.

## Research output

Useful upstream contributions include:

- redacted model and regulatory details;
- observed frequency and modulation;
- framing, timing, repetition, and command maps;
- comparisons across independent remotes;
- a family adapter with automated tests;
- physical replay validation and cross-device isolation results.

Raw `.sigmf-data` recordings stay local and are excluded from Git. Share only
deliberately selected, privacy-reviewed evidence when maintainers request it.
