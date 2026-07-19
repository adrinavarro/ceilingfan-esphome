# Learning a remote

Reliable learning depends more on controlled captures than on sophisticated signal
processing.

## Before recording

1. Identify the remote and fan model.
2. Photograph regulatory labels without including personal information.
3. Note the stated frequency, if present.
4. Put the RTL-SDR antenna close to the remote but not touching it.
5. Record the initial physical state of the fan and light.

## Recording rules

- Capture one semantic command at a time.
- Make at least three independent recordings per command.
- Press the button several times during each four-second recording.
- Release the button fully between presses.
- Keep the remote and antenna in the same positions.
- Reset the fan to a known state before state-dependent commands.
- Record wake-up presses separately; do not silently mix them with commands.

Use absolute commands where available. Incremental commands such as `speed_up` are
harder to expose as a synchronized Home Assistant entity.

## Pairing

Capture pairing only when the receiver requires it. A constant field may be a model
identifier, a remote address, or a value assigned during pairing. Do not claim that
a profile supports every unit of a model until a second independent remote has been
tested.

## Failure modes

Stop and investigate when:

- repeated presses produce structurally different frames;
- a field changes on every press;
- the learned waveform has low confidence;
- replay works only intermittently;
- the receiver stops accepting an old frame.

These can indicate noise, stateful commands, counters, checksums, or rolling codes.

