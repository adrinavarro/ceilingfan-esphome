# Voice assistants

The generated ESPHome firmware exposes one `fan` entity per profile and, when
learned, a corresponding `light` entity. A single ESP32 and CC1101 can therefore
represent several physical fans. ESPHome connects those entities to Home Assistant
through its native API; Alexa and Google Home do not consume that API directly.
The project CLI does consume it directly, so Home Assistant is optional for local
human or agent control. See [Local control without Home Assistant](local-control.md).

## Recommended architecture

For users who already run Home Assistant, the recommended local path is:

```text
ESP32 + CC1101 (one or more fan profiles)
      |
      | ESPHome native API over the local network
      v
Home Assistant fan and light entities for each profile
      |
      | Home Assistant Matter Hub
      v
Matter bridge
      |
      +----> Amazon Alexa
      +----> Google Home
      +----> Apple Home or another Matter controller
```

[Home Assistant Matter Hub](https://github.com/RiDDiX/home-assistant-matter-hub)
is an actively maintained community project, not an official Home Assistant or
`ceilingfan-esphome` component. It maps Home Assistant `fan` and `light` entities to the
corresponding Matter device types and communicates locally with Matter controllers.

## Home Assistant Matter Hub setup

1. Complete the `ceilingfan-esphome` workflow and add the ESPHome device to Home
   Assistant.
2. Confirm that the fan and light work correctly from Home Assistant before adding
   another integration layer.
3. Install Home Assistant Matter Hub. Home Assistant OS users can install the
   [RiDDiX add-on repository](https://github.com/riddix/home-assistant-addons); Docker
   and npm installations are also documented by the project.
4. Give every generated entity a clear room-specific name, then add a dedicated
   entity label such as `Voice Control` to the fan and light entities that should be
   available by voice.
5. Create a Matter bridge and filter it with `entity_label: Voice Control`. An
   entity-level label is safer than exposing every `fan` and `light` in the Home
   Assistant instance.
6. If Alexa will commission the bridge, use port `5540`; the current Matter Hub
   documentation identifies this as an Alexa pairing requirement.
7. Pair the bridge with the first Matter controller using its QR code.
8. To share the same bridge with another ecosystem, open a new commissioning window
   from the first controller or Matter Hub and use the newly generated code. A
   Matter commissioning code is not reusable indefinitely.

Matter relies on IPv6, UDP, and mDNS. VLANs or firewalls may require explicit local
network configuration. Alexa needs a compatible Amazon Matter controller, and
Google Home needs a compatible Google hub; an app or third-party voice speaker alone
may not be sufficient. Refer to the Matter Hub
[installation requirements](https://riddix.github.io/home-assistant-matter-hub/getting-started/installation),
[bridge configuration](https://riddix.github.io/home-assistant-matter-hub/getting-started/bridge-configuration),
and [controller compatibility matrix](https://riddix.github.io/home-assistant-matter-hub/guides/controller-compatibility)
because controller behavior changes over time.

## Other viable routes

| Route | Home Assistant required | Local control path | Relative effort | Recommendation |
|---|---:|---:|---:|---|
| `ceilingfan control` CLI, bridge web UI, or local agent | No | Yes | Low | Supported for direct control, but does not itself provide Alexa or Google Home integration. |
| Home Assistant + RiDDiX Matter Hub | Yes | Yes | Low to moderate | Recommended for existing Home Assistant users who want a free, cross-ecosystem bridge. |
| Home Assistant Cloud | Yes | Voice requests use a managed cloud integration | Low | Easiest officially supported Alexa and Google Home setup; requires a subscription. |
| Manual Home Assistant Alexa/Google integrations | Yes | No; external HTTPS/cloud services are involved | High | Viable for advanced users who accept DNS, TLS, cloud-console, and account-linking work. |
| Matter implemented directly on the ESP32 | No | Yes | Very high | Possible future backend, but outside the MVP. |
| Direct Alexa skill and Google cloud-to-cloud integration | No | No | Very high plus ongoing operations | Not recommended for this community hardware project. |

### Home Assistant Cloud

[Home Assistant Cloud](https://www.home-assistant.io/cloud) exposes selected Home
Assistant entities to Alexa and Google Assistant with a managed connection. It does
not require Matter Hub, public DNS, port forwarding, or a custom skill. This is the
lowest-effort route when a paid subscription is acceptable.

### Manual Home Assistant integrations

Home Assistant documents free manual integrations for both ecosystems, but the
operational surface is significantly larger:

- The [manual Alexa integration](https://www.home-assistant.io/integrations/alexa.smart_home/)
  uses an Alexa Smart Home skill and AWS Lambda.
- The [manual Google Assistant integration](https://www.home-assistant.io/integrations/google_assistant/)
  requires an externally reachable Home Assistant instance with a hostname and TLS,
  plus a Google Home Developer Console project.

These routes avoid a subscription but are not simpler than the Matter bridge for a
local-first installation.

## Why not expose Matter directly from `ceilingfan-esphome` now?

Direct Matter is technically feasible. Espressif's
[ESP-Matter SDK](https://docs.espressif.com/projects/esp-matter/en/latest/esp32/)
supports Wi-Fi ESP32 families, and Matter has native fan and light device types.
However, direct support would add substantial responsibilities:

- replace or deeply integrate with the current ESPHome firmware path;
- BLE/Wi-Fi commissioning and factory reset behavior;
- Matter fabrics, multi-admin state, IPv6, mDNS, and persistent storage;
- device attestation credentials and QR/setup-code generation;
- Matter fan and light clusters, state reporting, and controller quirks;
- a separate OTA, recovery, logging, and compatibility story;
- certification and production credentials if the project ever becomes a product.

Google's Matter guidance explicitly notes the potentially significant chipset and
software effort, while Amazon's production path includes Matter credentials and
certification requirements. Development credentials can be used for prototypes,
but that does not remove the implementation and support cost.

The learned device profile is intentionally independent of Home Assistant.
If direct Matter becomes worthwhile, it should be implemented as a second firmware
adapter:

```text
profiles/<fan>.yaml
       |
       +----> ESPHome adapter ----> Home Assistant ----> voice ecosystems
       |
       +----> Future Matter adapter ----> Alexa / Google / Apple directly
```

This preserves the learning workflow and avoids mixing Matter complexity into the
current ESPHome adapter. A second adapter should be added only when direct operation
without Home Assistant is a demonstrated user need.

## Project decision

The MVP supports the encrypted ESPHome native API for local CLI and agent control,
and Home Assistant as its ecosystem automation seam. The documented voice path is
Home Assistant Matter Hub, with Home Assistant Cloud as the easiest supported
alternative. Direct Matter remains a possible future adapter; custom Alexa and
Google cloud integrations are out of scope.
