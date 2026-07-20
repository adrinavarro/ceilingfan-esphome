# Captured protocol catalog

This catalog separates household inventory from decoded evidence. A commercial model
name is not itself a protocol guarantee: manufacturers may change RF hardware between
revisions without changing the product name.

## Inventory and support status

| Protocol family | Household remotes | Commercial models represented | RF behavior | Current support direction |
|---|---:|---|---|---|
| Inspire Pro / Arteconfort equivalent | 4 | Inspire Aveiro Pro, Bora Pro, Tavira Pro; equivalent Arteconfort models | Static, absolute speeds and brightness, unique 25-bit identity | First structured adapter and highest priority |
| Inspire YK8078 | 1 | Smaller-diameter Leroy Merlin Inspire model | Static, six speeds, mixed absolute and relative controls | Generic ESP32 raw learning implemented; structured adapter pending |
| CJOY | 1 | CJOY ceiling fan | 32-bit identity, 6-bit command, four-phase checksum | Experimental structured adapter; physical replay validation pending |
| Inspire Nashi | 1 | Leroy Merlin Inspire Nashi | Static, five speeds, relative fan/light toggles | Generic ESP32 raw learning implemented; structured adapter pending |
| Somfy RTS | 0 | Somfy-compatible blind/shutter/awning motors | 433.42 MHz, 24-bit address, rolling 16-bit code, public obfuscated frame | Experimental generated adapter (device class `roller_blind`); needs on-air validation |

Seven physical remotes are represented in the household inventory. Three distinct
Inspire Pro remote identities have been decoded so far; the fourth household unit is
part of the same observed remote family but still needs its own identity/profile before
deployment.

Single-example Nashi and YK8078 identities remain documentary evidence only. The
generic wizard has no model presets; each session calibrates against and learns the
complete waveform emitted by the user's own remote.

## Local evidence map

Raw SigMF data is intentionally ignored by Git, but the local capture layout records
where each result came from:

| Evidence | Local source |
|---|---|
| Inspire Pro remote A | Legacy bridge code and earlier captures |
| Inspire Pro remote B | `captures/remote-b/` |
| Inspire Pro remote C | `captures/remote-c/` |
| CJOY | `captures/remote-d/` |
| Inspire YK8078 | `captures/remote-e-yk8078/` |
| Inspire Nashi | `captures/remote-f/` |

`captures/remote-unknown/` was later identified as another capture of Inspire Pro
remote B, not a fourth remote identity.

## Detailed protocol notes

- [Inspire Pro and Arteconfort equivalents](inspire-arteconfort-protocol.md)
- [Inspire YK8078](protocols/inspire-yk8078.md)
- [CJOY four-phase protocol](protocols/cjoy-dynamic.md)
- [Inspire Nashi](protocols/inspire-nashi.md)
- [Somfy RTS (motorized blinds)](protocols/somfy-rts.md) — first non-fan device class

The bit strings in these documents use the demodulator's observed mark order. A future
adapter must validate bit ordering and replay against physical receivers before the
representation becomes a stable public profile schema.
