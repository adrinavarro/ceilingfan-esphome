# Local control without Home Assistant

The deployed bridge can be controlled directly from a computer, automation host, or
local agent. The CLI connects to the same encrypted ESPHome native API used by Home
Assistant; it does not expose an unauthenticated HTTP endpoint and does not bypass
the generated entity model.

```text
human or agent -> ceilingfan CLI -> encrypted ESPHome native API -> entity -> RF queue
Home Assistant -----------------------------^                        ^
phone browser  -> optional bridge web UI ----------------------------+
```

The caller needs local network access to the bridge and the API encryption key
created during hardware onboarding. Home Assistant and internet access are not
required.

## Phone and browser control

A bridge deployed with `firmware deploy --web-ui` serves its own control page at
`http://home-rf-bridge.local`, usable from any phone or browser on the local
network. It exposes the same generated fan, light, and button entities.

Access uses HTTP basic auth: user `admin`, password `web_password` from
`firmware/secrets.yaml` (generated automatically). Unlike the native API, the web
server is plain HTTP on the LAN — anyone who can read that traffic or guess the
password can operate the fans. That is an acceptable trade-off on a trusted home
network and the reason the web UI is opt-in rather than default. Omit `--web-ui`
to keep the encrypted native API as the only control surface.

## Discover the bridge

`firmware deploy` prints the bridge's final hostname. When it is unknown — a new
machine, a container, an agent bootstrapping itself — mDNS discovery finds it:

```sh
uv run ceilingfan control discover
uv run ceilingfan control discover --json
```

Discovery lists devices that advertise this project's firmware metadata.
Bridges deployed before that metadata existed only appear with `--all` (which
lists every ESPHome device) until they are redeployed. Discovery needs no API
key; controlling the bridge still does.

Exporting `CEILINGFAN_DEVICE` makes `--device` optional on every control
command, which keeps interactive use short and agent allowlists narrow:

```sh
export CEILINGFAN_DEVICE=home-rf-bridge.local
uv run ceilingfan control list
```

## Discover entity identifiers

From the repository, run:

```sh
uv run ceilingfan control list \
  --device home-rf-bridge.local
```

Use `--json` for a stable machine-readable response:

```sh
uv run ceilingfan control list \
  --device home-rf-bridge.local \
  --json
```

Commands accept either the exact entity name or its `object_id`. The `object_id` is
the safer agent-facing identifier because it is unambiguous and shell-friendly.

## Send commands

Turn on a fan at an absolute speed:

```sh
uv run ceilingfan control fan \
  --device home-rf-bridge.local \
  --entity main_bedroom_fan \
  --state on \
  --speed 4
```

Turn it off:

```sh
uv run ceilingfan control fan \
  --device home-rf-bridge.local \
  --entity main_bedroom_fan \
  --state off
```

Control a light. Brightness is normalized from `0` to `1` and is accepted only for
an entity that reports brightness support:

```sh
uv run ceilingfan control light \
  --device home-rf-bridge.local \
  --entity main_bedroom_fan_light \
  --state on \
  --brightness 0.5
```

Raw relative controls such as dimmer up, light toggle, warmth, or CJOY phase
synchronization are ESPHome button entities:

```sh
uv run ceilingfan control button \
  --device home-rf-bridge.local \
  --entity office_fan_dimmer_up
```

Add `--json` to any action when another program must parse the result. A successful
result says `status: sent` and always carries `acknowledged: false`: these consumer
RF protocols provide no physical acknowledgement, so a sent command never proves
that the receiver acted — the field makes that explicit to a parser or agent that
has not read this page. A failed `--json` command prints
`{"status": "error", "error": "..."}` on stdout and exits with a non-zero code, so
a parser never has to scrape stderr.

## API key handling

By default, the CLI reads `api_encryption_key` from `firmware/secrets.yaml`. That file
is generated locally and excluded from Git. Do not give it to an agent or process
that does not also need authority to control the bridge.

For a service account, container, or agent running outside the repository, provide
only that key through the process environment:

```sh
export CEILINGFAN_API_KEY="<the api_encryption_key value>"
ceilingfan control list --device home-rf-bridge.local --json
```

The export is illustrative. For an unattended process, inject the variable through
its secret manager rather than typing the value into an interactive shell.

Install the command on a machine without the checkout directly from GitHub. The
control-only install is deliberately small — no ESPHome tooling and no numpy:

```sh
uv tool install git+https://github.com/adrinavarro/ceilingfan-esphome
```

For a one-off invocation without installing anything, `uvx` works too:

```sh
uvx --from git+https://github.com/adrinavarro/ceilingfan-esphome \
  ceilingfan control list --device home-rf-bridge.local --json
```

Alternatively, let the agent run the documented `uv run ceilingfan ...` form in the
checkout.
The key is never required as a command-line argument, so it need not appear in command
history or process arguments.

## Agent and OpenClaw contract

Give the agent a narrow command allowlist instead of arbitrary ESPHome access:

```text
ceilingfan control discover --json
ceilingfan control list   --device <bridge> --json
ceilingfan control fan   --device <bridge> --entity <object_id> --state on|off [--speed N] --json
ceilingfan control light --device <bridge> --entity <object_id> --state on|off [--brightness 0..1] --json
ceilingfan control button --device <bridge> --entity <object_id> --json
```

An OpenClaw tool can invoke those commands through its local command runner with
`CEILINGFAN_API_KEY` (and optionally `CEILINGFAN_DEVICE`, which removes the
`--device` argument) stored in the runner's secret environment. Its first step
should be `control list --json`; the resulting entity IDs become the allowed
targets for later intent-to-command mapping. RF timings, remote IDs, and profile
internals never need to enter the agent prompt.

## Scheduled control without Home Assistant

Time-based automation does not need Home Assistant either: any always-on machine
on the local network can drive the bridge from cron. With the CLI installed as a
tool (`uv tool install git+...`), a crontab like this turns a bedroom fan on for
the siesta and off afterwards:

```crontab
CEILINGFAN_DEVICE=home-rf-bridge.local
30 15 * * * ceilingfan control fan --entity bedroom_fan --state on --speed 2 --json
0  17 * * * ceilingfan control fan --entity bedroom_fan --state off --json
```

`CEILINGFAN_API_KEY` must reach the jobs through cron's environment or a small
wrapper script that reads it from the machine's secret store — do not write the
key into the crontab of a shared machine. Remember that cron's `PATH` is minimal;
use the absolute path to `ceilingfan` (for a uv tool install, typically
`~/.local/bin/ceilingfan`) if the jobs do not start.

## State limitations

Most supported remotes are one-way. ESPHome, the CLI, Home Assistant, and the
physical remote can therefore disagree about current fan or light state. Absolute
`fan_off`, speed, light-on/off, and brightness commands recover on the next explicit
command. Relative toggle and dimmer buttons cannot promise synchronized state. CJOY
may additionally require its generated `synchronize RF phase` button after the
physical remote has transmitted.
