# One bridge for a multi-fan home

One ESP32 and one CC1101 can expose several physical ceiling fans. Each fan keeps a
separate profile, remote identity, entity name, and RF commands; the bridge serializes
all transmissions through its single radio.

This works when every profile uses the same modulation and the installed CC1101 and
antenna cover every configured frequency. It does not make a 433 MHz radio control a
2.4 GHz or otherwise unsupported fan. The bridge must also be physically within RF
range of every receiver.

## Initial five-fan installation

### 1. Flash the learning bridge once

Connect the assembled ESP32 and CC1101 to the computer over USB:

```sh
uv run ceilingfan hardware onboard --port /dev/ttyUSB0
```

After this succeeds, USB data is no longer required. Leave the bridge powered from
the computer or move it to an ordinary USB power supply. Learning and deployment use
Wi-Fi.

### 2. Learn all five fans before deploying final firmware

Keep the learning firmware installed while creating every profile. Run the wizard
once per physical fan with a unique room-specific name; each profile lands in
`profiles/<name-slug>.yaml` automatically:

```sh
uv run ceilingfan learn wizard \
  --device ceilingfan-learning.local \
  --name "Main bedroom fan"

uv run ceilingfan learn wizard \
  --device ceilingfan-learning.local \
  --name "Second bedroom fan"

uv run ceilingfan learn wizard \
  --device ceilingfan-learning.local \
  --name "Office fan"

uv run ceilingfan learn wizard \
  --device ceilingfan-learning.local \
  --name "Living room fan"

uv run ceilingfan learn wizard \
  --device ceilingfan-learning.local \
  --name "Kitchen fan"
```

For each fan, use only its own original remote during that wizard session. An Inspire
Pro observation automatically selects fast identity-based onboarding. An unrecognized
static ASK/OOK remote stays in the generic button-by-button flow. Do not touch the
receiver pairing button.

Profile names must remain unique after punctuation and spaces are normalized. Names
such as `Bedroom fan` and `Bedroom-fan` would both produce `bedroom_fan` and are
therefore rejected.

### 3. Deploy all profiles together once

With every profile in `profiles/`, the firmware commands find them automatically
and print the list they will use — no repetition, and no way to silently forget a
fan. Explicit `--profile` options remain available for a partial build.

```sh
uv run ceilingfan firmware doctor

uv run ceilingfan firmware deploy \
  --bridge-name "Home RF bridge" \
  --device ceilingfan-learning.local \
  --web-ui
```

`--web-ui` optionally serves a phone/browser control page from the bridge; see
[Local control](local-control.md).

The deploy prints the final hostname derived from this bridge name:
`home-rf-bridge.local` (or find it later with `ceilingfan control discover`). If
mDNS is unavailable or still updating, use the bridge's IP address instead. Keep
all five profile files: they are source inputs for every future firmware rebuild.

### 4. Verify the entity boundary

Home Assistant is not required for this check:

```sh
uv run ceilingfan control list \
  --device home-rf-bridge.local

uv run ceilingfan control fan \
  --device home-rf-bridge.local \
  --entity main_bedroom_fan \
  --state on \
  --speed 3
```

The list should contain separate fan, light, and relative-command button entities
for the corresponding profiles. Then run
`ceilingfan firmware validate --device home-rf-bridge.local`, which sends every
command in turn and records whether the intended physical receiver — and no other
fan — reacted, before adding Home Assistant or a voice-assistant bridge.

## Add another fan later

The final firmware is transmitter-only, while learning requires the receiver
firmware. The transition is still entirely OTA:

1. Keep every existing profile file.
2. Temporarily install learning firmware over Wi-Fi:

   ```sh
   uv run ceilingfan learn prepare --device home-rf-bridge.local
   ```

   During this temporary mode, normal fan entities are unavailable. The device comes
   back as `ceilingfan-learning.local` and will usually retain its DHCP address.
3. Learn only the new fan into a sixth profile:

   ```sh
   uv run ceilingfan learn wizard \
     --device ceilingfan-learning.local \
     --name "Guest room fan"
   ```

4. Run `ceilingfan firmware deploy` again. It picks up all six profiles from
   `profiles/` automatically; verify the printed list before it flashes. Target
   `ceilingfan-learning.local` and use the same bridge name as before.
5. List and physically validate all entities again.

No USB connection or re-pairing is required unless Wi-Fi or OTA recovery fails.
