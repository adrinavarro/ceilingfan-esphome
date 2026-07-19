# Ceiling Fan RF Bridge

This context describes how physical ceiling fans, their RF remotes, and one shared
ESPHome RF bridge relate to each other.

## Language

**RF Bridge**:
One installed ESP32 and CC1101 that transmits commands for one or more fan installations.
_Avoid_: Fan controller, remote clone

**Control Entity**:
The generated ESPHome fan, light, or stateless button boundary used equally by the
local CLI, agents, and Home Assistant. It hides RF command keys and radio timing.
_Avoid_: RF command, Home Assistant entity

**Fan Installation**:
One physical fan receiver in one room, addressed through the remote identity it has learned.
_Avoid_: Fan model, remote

**Device Profile**:
The durable description of one fan installation: its protocol family, remote identity,
capabilities, and command semantics.
_Avoid_: Model profile, universal remote

**Protocol Family**:
A shared RF frame structure, timing scheme, and command vocabulary used by one or
more commercial fan models.
_Avoid_: Fan model, brand protocol

**Remote Identity**:
The fixed address-like field that distinguishes one physical remote or paired fan
installation from another within the same protocol family.
_Avoid_: Pairing code, model ID

**Absolute Command**:
A command whose payload names the resulting state, such as fan speed 4 or light
brightness 6.
_Avoid_: Stateful button

**Relative Command**:
A command whose result depends on the receiver's current state, such as toggle or
dim up.
_Avoid_: Absolute state

**Dynamic Command**:
A command containing a counter, rolling value, checksum, or other field that changes
between equivalent button events.
_Avoid_: Static waveform

**Protocol Phase**:
A small per-installation state advanced by a protocol adapter for each semantic
button event. It may require explicit synchronization after another transmitter is
used.
_Avoid_: Fan state, remote identity

**Protocol Adapter**:
The protocol-family knowledge that turns a semantic command and remote identity into
a valid RF transmission.
_Avoid_: Device profile, fan driver

**Raw Waveform**:
A captured, replayable sequence of RF mark and space timings that requires no
bit-level protocol interpretation.
_Avoid_: Protocol adapter

**Learning Firmware**:
The receiver firmware (`firmware/learning.yaml`, hostname
`ceilingfan-learning.local`) that streams RF observations while profiles are being
learned. `hardware onboard` installs it over USB once; `learn prepare` reinstalls
it over OTA.
_Avoid_: Onboarding firmware, receiver mode

**Final Firmware**:
The generated transmitter firmware that exposes one control entity set per device
profile. It does not run the learning receiver.
_Avoid_: Production firmware, generated.yaml (that is its file, not the concept)
