from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from . import __version__
from .bridge_learning import (
    BridgeObservation,
    FamilyObservation,
    StaticFingerprint,
    build_bridge_profile,
    command_names,
    load_bridge_evidence,
    parse_bridge_observation,
    parse_family_observation,
    save_bridge_evidence,
    validate_fingerprint,
)
from .control import (
    DEVICE_ENVIRONMENT_VARIABLE,
    control_device,
    discover_bridges,
    inspect_device,
    load_api_key,
    resolve_device,
)
from .esphome import (
    create_secrets,
    ensure_web_password,
    hostname_slug,
    label_entity_warnings,
    require_command,
    run_esphome,
    run_esphome_logs,
    validation_steps,
    write_firmware,
)
from .models import CeilingFanError, DeviceProfile
from .protocols import build_cjoy_profile, build_inspire_pro_profile

RESEARCH_INSTALL_HINT = "uv sync --extra research"


def _import_research(module: str):
    # numpy stays out of the base install; only the RTL-SDR laboratory needs it.
    try:
        return importlib.import_module(f".{module}", __package__)
    except ModuleNotFoundError as exc:
        raise CeilingFanError(
            "The research commands need the optional numpy dependency. "
            f"Install it with: {RESEARCH_INSTALL_HINT}"
        ) from exc


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _frequency(value: str) -> int:
    normalized = value.strip().lower().replace("hz", "")
    multiplier = 1
    if normalized.endswith("m"):
        multiplier, normalized = 1_000_000, normalized[:-1]
    elif normalized.endswith("k"):
        multiplier, normalized = 1_000, normalized[:-1]
    return int(float(normalized) * multiplier)


def _integer(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer such as 123 or 0x1A2B") from exc


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _unit_float(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
    return number


def _add_profile_arguments(command: argparse.ArgumentParser, verb: str) -> None:
    command.add_argument(
        "--profile",
        type=Path,
        action="append",
        help=f"Device profile to {verb}. Repeat for multiple fans; omit to use "
        "every profile in --profiles-dir.",
    )
    command.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("profiles"),
        help="Directory searched for *.yaml profiles when --profile is omitted.",
    )


def _add_control_connection_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--device",
        help="Bridge hostname or IP address; defaults to "
        f"${DEVICE_ENVIRONMENT_VARIABLE}.",
    )
    command.add_argument("--port", type=_positive_int, default=6053)
    command.add_argument(
        "--secrets",
        type=Path,
        default=Path("firmware/secrets.yaml"),
        help="ESPHome secrets file; CEILINGFAN_API_KEY takes precedence.",
    )
    command.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )


def _add_rtl_commands(commands: argparse._SubParsersAction) -> None:
    scan = commands.add_parser("scan", help="Advanced: scan with an RTL-SDR.")
    scan.add_argument("--start", type=_frequency, default=420_000_000)
    scan.add_argument("--end", type=_frequency, default=450_000_000)
    scan.add_argument("--bin", type=_frequency, default=10_000)
    scan.add_argument("--duration", default="30s")
    scan.add_argument("--output", type=Path, default=Path("captures/scan.csv"))

    capture = commands.add_parser("capture", help="Advanced: record RTL-SDR I/Q data.")
    capture.add_argument("label", help="Semantic label, for example fan_speed_1.")
    capture.add_argument("--frequency", type=_frequency, required=True)
    capture.add_argument("--sample-rate", type=_frequency, default=1_024_000)
    capture.add_argument("--gain", type=float, default=20.0)
    capture.add_argument("--duration", type=_positive_float, default=4.0)
    capture.add_argument("--attempt", type=int, default=1)
    capture.add_argument("--directory", type=Path, default=Path("captures"))

    analyze = commands.add_parser(
        "analyze", help="Advanced: learn static OOK waveforms from RTL-SDR captures."
    )
    analyze.add_argument("--captures", type=Path, default=Path("captures"))
    analyze.add_argument("--name", required=True, help="Friendly device name.")
    analyze.add_argument("--output", type=Path, default=Path("device-profile.yaml"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ceilingfan",
        description="Learn and deploy a local RF ceiling fan bridge.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    phases = parser.add_subparsers(dest="phase", required=True)

    learn = phases.add_parser("learn", help="Learn a remote with the ESP32 and CC1101 bridge.")
    learn_commands = learn.add_subparsers(dest="action", required=True)
    learn_commands.add_parser("doctor", help="Check bridge-based learning requirements.")
    listen = learn_commands.add_parser(
        "listen", help="Diagnostic: stream decoded and raw RF observations."
    )
    listen.add_argument("--device", default="ceilingfan-learning.local")
    listen.add_argument("--config", type=Path, default=Path("firmware/learning.yaml"))
    prepare = learn_commands.add_parser(
        "prepare",
        help="OTA-install the learning firmware before learning another fan.",
    )
    prepare.add_argument("--device", required=True, help="Current bridge hostname or IP.")
    prepare.add_argument(
        "--config", type=Path, default=Path("firmware/learning.yaml")
    )
    inspire_pro = learn_commands.add_parser(
        "inspire-pro",
        help="Advanced: create an Inspire Pro profile from a known remote ID.",
    )
    inspire_pro.add_argument("--remote-id", type=_integer, required=True)
    inspire_pro.add_argument("--name", required=True)
    inspire_pro.add_argument(
        "--output",
        type=Path,
        help="Profile path; defaults to profiles/<name-slug>.yaml.",
    )
    cjoy = learn_commands.add_parser(
        "cjoy",
        help="Advanced: create an experimental CJOY profile from a known remote ID.",
    )
    cjoy.add_argument("--remote-id", type=_integer, required=True)
    cjoy.add_argument("--name", required=True)
    cjoy.add_argument(
        "--output",
        type=Path,
        help="Profile path; defaults to profiles/<name-slug>.yaml.",
    )
    # "raw" is a legacy alias for the wizard; it keeps working but stays out
    # of the help listing (no help text) to avoid suggesting two workflows.
    for action, help_text in (
        ("wizard", "Learn any supported remote; detects known families automatically."),
        ("raw", None),
    ):
        raw = learn_commands.add_parser(
            action, **({} if help_text is None else {"help": help_text})
        )
        raw.add_argument("--name", required=True, help="Friendly fan name.")
        raw.add_argument(
            "--command",
            action="append",
            help="Semantic command label. Repeat, or omit to let the wizard "
            "identify the remote first and ask only when needed.",
        )
        raw.add_argument("--attempts", type=_positive_int, default=1)
        raw.add_argument(
            "--resume",
            action="store_true",
            help="Continue from an existing evidence file instead of replacing it.",
        )
        raw.add_argument("--timeout", type=_positive_float, default=90.0)
        raw.add_argument("--device", default="ceilingfan-learning.local")
        raw.add_argument("--config", type=Path, default=Path("firmware/learning.yaml"))
        raw.add_argument(
            "--output",
            type=Path,
            help="Profile path; defaults to profiles/<name-slug>.yaml.",
        )
        raw.add_argument(
            "--evidence",
            type=Path,
            help="Observation YAML path; defaults beside the generated profile.",
        )
        raw.add_argument(
            "--verbose",
            action="store_true",
            help="Stream the full ESPHome log instead of only RF observations.",
        )

    research = phases.add_parser(
        "research", help="Optional RTL-SDR laboratory for unsupported protocols."
    )
    research_commands = research.add_subparsers(dest="action", required=True)
    research_commands.add_parser("doctor", help="Check optional RTL-SDR tools.")
    _add_rtl_commands(research_commands)

    hardware = phases.add_parser(
        "hardware", help="Prepare the assembled ESP32 and CC1101 using only USB."
    )
    hardware_commands = hardware.add_subparsers(dest="action", required=True)
    hardware_commands.add_parser("doctor", help="Check ESPHome and learning firmware files.")
    onboard = hardware_commands.add_parser(
        "onboard", help="Create secrets and flash the learning firmware over USB."
    )
    onboard.add_argument("--port", required=True, help="Serial port, such as /dev/ttyUSB0.")
    onboard.add_argument("--config", type=Path, default=Path("firmware/learning.yaml"))
    onboard.add_argument("--secrets", type=Path, default=Path("firmware/secrets.yaml"))

    firmware = phases.add_parser(
        "firmware", help="Generate, deploy, and validate final firmware over the network."
    )
    firmware_commands = firmware.add_subparsers(dest="action", required=True)
    firmware_doctor = firmware_commands.add_parser(
        "doctor", help="Check ESPHome and learned profile files."
    )
    _add_profile_arguments(firmware_doctor, "check")

    build = firmware_commands.add_parser(
        "build", help="Generate ESPHome firmware from one or more profiles."
    )
    _add_profile_arguments(build, "expose")
    build.add_argument("--bridge-name", help="ESPHome bridge name.")
    build.add_argument("--output", type=Path, default=Path("firmware/generated.yaml"))
    build.add_argument(
        "--web-ui",
        action="store_true",
        help="Serve a local phone/browser control page with HTTP basic auth.",
    )

    deploy = firmware_commands.add_parser(
        "deploy", help="Build and install learned firmware over OTA."
    )
    _add_profile_arguments(deploy, "expose")
    deploy.add_argument("--bridge-name", help="ESPHome bridge name.")
    deploy.add_argument("--output", type=Path, default=Path("firmware/generated.yaml"))
    deploy.add_argument("--device", required=True, help="Device hostname or IP address.")
    deploy.add_argument(
        "--web-ui",
        action="store_true",
        help="Serve a local phone/browser control page with HTTP basic auth.",
    )

    validate = firmware_commands.add_parser(
        "validate", help="Record physical validation for each learned command."
    )
    _add_profile_arguments(validate, "validate")
    validate.add_argument("--output", type=Path, default=Path("validation.json"))
    validate.add_argument(
        "--device",
        help="Deployed bridge hostname or IP. When given, each command is sent "
        "automatically before asking for the physical result.",
    )
    validate.add_argument("--port", type=_positive_int, default=6053)
    validate.add_argument(
        "--secrets",
        type=Path,
        default=Path("firmware/secrets.yaml"),
        help="ESPHome secrets file; CEILINGFAN_API_KEY takes precedence.",
    )

    control = phases.add_parser(
        "control", help="Control deployed ESPHome entities without Home Assistant."
    )
    control_commands = control.add_subparsers(dest="action", required=True)
    discover = control_commands.add_parser(
        "discover", help="Find ceilingfan bridges on the local network via mDNS."
    )
    discover.add_argument(
        "--timeout", type=_positive_float, default=5.0, help="Browse time in seconds."
    )
    discover.add_argument(
        "--all",
        action="store_true",
        help="List every ESPHome device, including bridges deployed before "
        "discovery metadata existed.",
    )
    discover.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    control_list = control_commands.add_parser(
        "list", help="List controllable fan, light, and button entities."
    )
    _add_control_connection_arguments(control_list)

    control_fan = control_commands.add_parser("fan", help="Control a fan entity.")
    _add_control_connection_arguments(control_fan)
    control_fan.add_argument("--entity", required=True, help="Entity object_id or exact name.")
    control_fan.add_argument("--state", required=True, choices=("on", "off"))
    control_fan.add_argument("--speed", type=_positive_int)

    control_light = control_commands.add_parser("light", help="Control a light entity.")
    _add_control_connection_arguments(control_light)
    control_light.add_argument(
        "--entity", required=True, help="Entity object_id or exact name."
    )
    control_light.add_argument("--state", required=True, choices=("on", "off"))
    control_light.add_argument("--brightness", type=_unit_float)

    control_button = control_commands.add_parser(
        "button", help="Press a stateless or relative-command entity."
    )
    _add_control_connection_arguments(control_button)
    control_button.add_argument(
        "--entity", required=True, help="Entity object_id or exact name."
    )
    return parser


def cmd_doctor(phase: str, profile_paths: list[Path] | None = None) -> int:
    required_commands = {
        "learn": ("esphome",),
        "research": ("rtl_sdr", "rtl_power", "rtl_test"),
        "hardware": ("esphome",),
        "firmware": ("esphome",),
    }[phase]
    install_hints = {
        "esphome": "install with: uv sync --extra firmware",
        "rtl_sdr": "install the rtl-sdr tools, e.g. brew install librtlsdr",
        "rtl_power": "install the rtl-sdr tools, e.g. brew install librtlsdr",
        "rtl_test": "install the rtl-sdr tools, e.g. brew install librtlsdr",
    }
    checks = {name: shutil.which(name) for name in required_commands}
    failed = False
    print(f"Checking the {phase} phase. No other phase hardware is required.\n")
    for name, path in checks.items():
        status = path or f"MISSING ({install_hints[name]})"
        print(f"{name:12} {status}")
        failed |= path is None
    if phase == "research":
        has_numpy = importlib.util.find_spec("numpy") is not None
        status = (
            "installed" if has_numpy else f"MISSING (install with: {RESEARCH_INSTALL_HINT})"
        )
        print(f"{'numpy':12} {status}")
        failed |= not has_numpy
    required_files: tuple[Path, ...] = {
        "learn": (Path("firmware/learning.yaml"),),
        "research": (),
        "hardware": (Path("firmware/learning.yaml"),),
        "firmware": tuple(profile_paths or [Path("device-profile.yaml")])
        + (Path("firmware/secrets.yaml"),),
    }[phase]
    for path in required_files:
        exists = path.exists()
        print(f"{str(path):28} {'FOUND' if exists else 'MISSING'}")
        failed |= not exists
    if failed:
        print(f"\nResolve the missing {phase} requirements before continuing.")
        return 1
    print(f"\nThe {phase} phase is ready.")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    executable = require_command("rtl_power")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frequency_range = f"{args.start}:{args.end}:{args.bin}"
    print("Press remote buttons repeatedly during the scan.")
    subprocess.run(
        [executable, "-f", frequency_range, "-i", "1", "-e", args.duration, str(args.output)],
        check=True,
    )
    print(f"Scan written to {args.output}")
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    sigmf = _import_research("sigmf")
    executable = require_command("rtl_sdr")
    args.directory.mkdir(parents=True, exist_ok=True)
    stem = f"{args.label}-{args.attempt:02d}"
    data_path = args.directory / f"{stem}.sigmf-data"
    sample_count = round(args.sample_rate * args.duration)
    print(f"Recording {args.duration:g}s. Press only '{args.label}' several times now.")
    subprocess.run(
        [
            executable,
            "-f", str(args.frequency),
            "-s", str(args.sample_rate),
            "-g", str(args.gain),
            "-n", str(sample_count),
            str(data_path),
        ],
        check=True,
    )
    meta_path = sigmf.write_metadata(
        data_path,
        label=args.label,
        sample_rate=args.sample_rate,
        frequency_hz=args.frequency,
        gain_db=args.gain,
    )
    print(f"Capture written to {data_path} and {meta_path}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    analysis = _import_research("analysis")
    paths = sorted(args.captures.glob("*.sigmf-meta"))
    profile = analysis.learn_profile(paths, args.name)
    profile.save(args.output)
    print(f"Learned {len(profile.commands)} commands and wrote {args.output}")
    for label, command in sorted(profile.commands.items()):
        print(
            f"  {label}: {command.repetitions} repetitions, "
            f"confidence {command.confidence:.1%}"
        )
    return 0


def cmd_listen(args: argparse.Namespace) -> int:
    print("Listening through the ESP32 + CC1101 bridge. Press Ctrl-C when finished.")
    print("Look for a CFLEARN family/remote_id line or a generic CFRAW observation.")
    run_esphome_logs(args.config, args.device)
    return 0


def cmd_prepare_learning(args: argparse.Namespace) -> int:
    run_esphome(args.config, args.device)
    print(
        "Learning firmware installed. The bridge is now reachable as "
        "ceilingfan-learning.local or by its IP address."
    )
    print(
        'Next: ceilingfan learn wizard --name "Guest room fan" '
        "(normal control stays unavailable until the final firmware is redeployed)."
    )
    return 0


def _profile_output_path(name: str, output: Path | None) -> Path:
    return output if output is not None else Path("profiles") / f"{hostname_slug(name)}.yaml"


def _print_label_warnings(labels: list[str]) -> None:
    for warning in label_entity_warnings(labels):
        print(f"warning: {warning}")


def _print_learn_next_step(device: str) -> None:
    print(
        "Next: learn another fan with its own remote, or deploy every profile "
        f"in profiles/ with: ceilingfan firmware deploy --device {device}"
    )


def cmd_inspire_pro(args: argparse.Namespace) -> int:
    output = _profile_output_path(args.name, args.output)
    profile = build_inspire_pro_profile(args.name, args.remote_id)
    profile.save(output)
    print(
        f"Created Inspire Pro profile {output} for remote ID "
        f"0x{args.remote_id:07X}"
    )
    return 0


def cmd_cjoy(args: argparse.Namespace) -> int:
    output = _profile_output_path(args.name, args.output)
    profile = build_cjoy_profile(args.name, args.remote_id)
    profile.save(output)
    print(
        f"Created experimental CJOY profile {output} for remote ID "
        f"0x{args.remote_id:08X}"
    )
    return 0


def _next_learning_observation(
    observations: queue.Queue[BridgeObservation],
    families: queue.Queue[FamilyObservation],
    process: subprocess.Popen[str],
    timeout: float,
    recent_lines: deque[str],
) -> BridgeObservation | FamilyObservation:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return families.get_nowait()
        except queue.Empty:
            pass
        try:
            observation = observations.get(
                timeout=min(0.25, deadline - time.monotonic())
            )
            try:
                # Known-family firmware logs follow the generic observation for
                # the same RF event. Prefer that deeper adapter when it arrives.
                return families.get(timeout=0.5)
            except queue.Empty:
                return observation
        except queue.Empty:
            if process.poll() is not None:
                tail = "\n".join(recent_lines).rstrip()
                detail = f"\nRecent log output:\n{tail}" if tail else ""
                raise CeilingFanError(
                    "ESPHome log stream stopped with exit code "
                    f"{process.returncode}{detail}"
                )
    raise CeilingFanError(
        "Timed out waiting for a repeated RF frame. Check the remote's battery "
        "and distance to the bridge, or rerun with --verbose for the full log."
    )


def _wizard_command_names(existing: list[str] | None = None) -> list[str]:
    entered = list(existing or [])
    if entered:
        print("Evidence already contains: " + ", ".join(sorted(entered)))
        print("Add further command labels, or leave blank to continue with those.")
    else:
        print("Name the controls printed on this remote; no model preset is used.")
    print(
        "Examples: fan_off, fan_toggle, fan_speed_1, light_toggle, "
        "dimmer_up, color_temperature_warm."
    )
    while True:
        value = input("Next command label (leave blank when finished): ").strip()
        if not value:
            break
        entered.append(value)
    return command_names(entered)


def _family_profile(name: str, event: FamilyObservation):
    if event.family == "inspire_pro":
        return build_inspire_pro_profile(name, event.remote_id)
    if event.family == "cjoy":
        return build_cjoy_profile(name, event.remote_id)
    return None


def cmd_raw(args: argparse.Namespace) -> int:
    output = _profile_output_path(args.name, args.output)
    labels = command_names(args.command) if args.command else None
    evidence_path = args.evidence or output.with_suffix(".observations.yaml")
    learned: dict[str, list[BridgeObservation]] = {}
    fingerprint: StaticFingerprint | None = None
    if evidence_path.exists():
        if not args.resume:
            raise CeilingFanError(
                f"Evidence already exists at {evidence_path}; use --resume or move it"
            )
        evidence_name, fingerprint, learned = load_bridge_evidence(evidence_path)
        if evidence_name != args.name:
            raise CeilingFanError(
                f"Evidence belongs to '{evidence_name}', not '{args.name}'"
            )
        if labels is None:
            labels = _wizard_command_names(sorted(learned))
        unexpected = sorted(set(learned) - set(labels))
        if unexpected:
            raise CeilingFanError(
                "Evidence contains commands not requested now: " + ", ".join(unexpected)
            )
    if labels is not None:
        _print_label_warnings(labels)
        if all(len(learned.get(label, [])) >= args.attempts for label in labels):
            profile = build_bridge_profile(args.name, learned, fingerprint=fingerprint)
            profile.save(output)
            print(f"Rebuilt {output} from complete evidence in {evidence_path}")
            _print_learn_next_step(args.device)
            return 0

    executable = require_command("esphome")
    process = subprocess.Popen(
        [executable, "logs", str(args.config), "--device", args.device],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        process.terminate()
        raise CeilingFanError("Could not read the ESPHome log stream")

    received: queue.Queue[BridgeObservation] = queue.Queue()
    families: queue.Queue[FamilyObservation] = queue.Queue()
    recent_lines: deque[str] = deque(maxlen=30)

    def read_logs() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            recent_lines.append(line.rstrip("\n"))
            if args.verbose:
                print(line, end="")
            try:
                observation = parse_bridge_observation(line)
            except CeilingFanError as exc:
                print(f"Ignoring invalid CFRAW observation: {exc}")
                continue
            if observation is not None:
                received.put(observation)
            family = parse_family_observation(line)
            if family is not None:
                families.put(family)

    def drain_queues() -> None:
        for pending in (received, families):
            while True:
                try:
                    pending.get_nowait()
                except queue.Empty:
                    break

    def next_event() -> BridgeObservation | FamilyObservation:
        return _next_learning_observation(
            received, families, process, args.timeout, recent_lines
        )

    reader = threading.Thread(target=read_logs, daemon=True)
    reader.start()
    detected_profile = None
    try:
        print(
            "The bridge will learn one repeated button event at a time. "
            "Do not press the receiver pairing button."
        )
        if not args.verbose:
            print(
                f"Streaming RF observations from {args.device} "
                "(rerun with --verbose for the full ESPHome log)."
            )
        if labels is None:
            # Identify the remote before asking for anything: a recognized
            # protocol family needs no button labels at all.
            input(
                "Press Enter, then press any button on this fan's remote once "
                "to identify it... "
            )
            drain_queues()
            while True:
                event = next_event()
                if isinstance(event, FamilyObservation):
                    detected_profile = _family_profile(args.name, event)
                    if detected_profile is not None:
                        print(
                            f"Detected {event.family}; its family adapter provides "
                            "the complete command set. No buttons need naming."
                        )
                        break
                    continue
                fingerprint = StaticFingerprint.from_observation(event)
                print(
                    "No known protocol family recognized; learning button by "
                    "button. Calibrated this remote's RF fingerprint: "
                    f"{fingerprint.frame_pulses} pulses, gap {fingerprint.gap_us}us."
                )
                break
            if detected_profile is None:
                labels = _wizard_command_names()
                _print_label_warnings(labels)
        if detected_profile is None:
            assert labels is not None
            for label in labels:
                learned.setdefault(label, [])
                for attempt in range(len(learned[label]) + 1, args.attempts + 1):
                    input(
                        f"Ready for '{label}' ({attempt}/{args.attempts}). "
                        "Press Enter, then press that remote button once... "
                    )
                    drain_queues()
                    while True:
                        event = next_event()
                        if isinstance(event, FamilyObservation):
                            detected_profile = _family_profile(args.name, event)
                            if detected_profile is not None:
                                print(
                                    f"Detected {event.family}; using its structured "
                                    "family adapter."
                                )
                                break
                            continue
                        observation = event
                        if fingerprint is None:
                            fingerprint = StaticFingerprint.from_observation(
                                observation
                            )
                            print(
                                "Calibrated this remote's RF fingerprint: "
                                f"{fingerprint.frame_pulses} pulses, "
                                f"gap {fingerprint.gap_us}us."
                            )
                        else:
                            try:
                                validate_fingerprint(fingerprint, observation)
                            except CeilingFanError as exc:
                                print(f"Rejected RF event: {exc}")
                                print(f"Press '{label}' again...")
                                continue
                        break
                    if detected_profile is not None:
                        break
                    learned[label].append(observation)
                    print(
                        f"Captured {len(observation.frame_us)} pulses, "
                        f"{observation.repetitions} repeated frames, "
                        f"gap {observation.gap_us}us."
                    )
                if detected_profile is not None:
                    break
    except (KeyboardInterrupt, EOFError) as exc:
        raise CeilingFanError(
            f"Learning interrupted; partial evidence will be saved to {evidence_path}"
        ) from exc
    finally:
        if detected_profile is None and any(learned.values()):
            save_bridge_evidence(
                evidence_path, args.name, learned, fingerprint=fingerprint
            )
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(timeout=1)

    profile = detected_profile or build_bridge_profile(
        args.name, learned, fingerprint=fingerprint
    )
    profile.save(output)
    if detected_profile is None:
        print(f"Evidence written to {evidence_path}")
    print(f"Learned {len(profile.command_names())} commands and wrote {output}")
    _print_learn_next_step(args.device)
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    if args.secrets.exists():
        print(f"{args.secrets} already exists.")
        print(
            "Replacing it generates a new API encryption key, OTA password, and "
            "web password. Any bridge flashed with the current secrets will "
            "refuse OTA updates and API connections until it is onboarded "
            "again over USB."
        )
        answer = input("Replace it? [y/N] ").strip().lower()
        if answer != "y":
            raise CeilingFanError("Onboarding cancelled")
    ssid = input("Wi-Fi SSID: ").strip()
    wifi_password = getpass.getpass("Wi-Fi password: ")
    if not ssid or not wifi_password:
        raise CeilingFanError("Wi-Fi SSID and password are required")
    create_secrets(args.secrets, ssid, wifi_password)
    run_esphome(args.config, args.port)
    print(
        "\nLearning bridge ready as ceilingfan-learning.local. It can now run "
        "from any USB power supply."
    )
    print('Next: ceilingfan learn wizard --name "Bedroom fan" (once per fan).')
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    bridges = discover_bridges(timeout=args.timeout, all_devices=args.all)
    if args.json:
        print(json.dumps({"bridges": [bridge.to_dict() for bridge in bridges]}, indent=2))
        return 0
    if not bridges:
        print("No ceilingfan bridges found on the local network.")
        print(
            "Bridges deployed before discovery metadata existed do not "
            "advertise themselves; try --all, or redeploy the firmware."
        )
        return 0
    print(f"Found {len(bridges)} device(s):")
    for bridge in bridges:
        address = bridge.address or "?"
        print(f"  {bridge.hostname:32} {address:16} {bridge.name}")
    print("Use one with: ceilingfan control list --device <hostname>")
    return 0


def cmd_control(args: argparse.Namespace) -> int:
    if args.action == "discover":
        return cmd_discover(args)
    device = resolve_device(args.device)
    api_key = load_api_key(args.secrets)
    if args.action == "list":
        entities = asyncio.run(inspect_device(device, args.port, api_key))
        payload = {
            "device": device,
            "entities": [entity.to_dict() for entity in entities],
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"Controllable entities on {device}:")
            for entity in entities:
                capabilities = []
                if entity.speed_count:
                    capabilities.append(f"speeds=1-{entity.speed_count}")
                if entity.supports_brightness:
                    capabilities.append("brightness=0..1")
                suffix = f" [{', '.join(capabilities)}]" if capabilities else ""
                print(f"  {entity.type:6} {entity.object_id:36} {entity.name}{suffix}")
        return 0

    state = getattr(args, "state", None)
    speed = getattr(args, "speed", None)
    brightness = getattr(args, "brightness", None)
    if state == "off" and speed is not None:
        raise CeilingFanError("--speed can only be used with --state on")
    if state == "off" and brightness is not None:
        raise CeilingFanError("--brightness can only be used with --state on")
    result = asyncio.run(
        control_device(
            device,
            args.port,
            api_key,
            args.action,
            args.entity,
            state=None if state is None else state == "on",
            speed=speed,
            brightness=brightness,
        )
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            f"Sent {args.action} command to {result.entity.name} "
            f"({result.entity.object_id}) on {device}."
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    profiles = [DeviceProfile.load(path) for path in _profile_paths(args)]
    steps = validation_steps(profiles)
    api_key = load_api_key(args.secrets) if args.device else None
    if args.device:
        print(
            f"Each command will be sent to {args.device} before asking for the "
            "physical result. Watch the intended fan — and check that no other "
            "fan reacts."
        )
    else:
        print(
            "Trigger each command from the local CLI or Home Assistant, then "
            "record the physical result. Pass --device to send each command "
            "automatically."
        )
    results: dict[str, dict[str, dict[str, str]]] = {
        profile.name: {} for profile in profiles
    }
    for step in steps:
        if args.device:
            print(f"Sending '{step.profile_name}: {step.command}'...")
            try:
                asyncio.run(
                    control_device(
                        args.device,
                        args.port,
                        api_key,
                        step.entity_type,
                        step.object_id,
                        state=step.state,
                        speed=step.speed,
                        brightness=step.brightness,
                    )
                )
            except CeilingFanError as exc:
                print(f"error: {exc}")
                results[step.profile_name][step.command] = {
                    "result": "error",
                    "error": str(exc),
                }
                continue
        answer = input(
            f"Did '{step.profile_name}: {step.command}' work correctly? [y/n/s] "
        ).strip().lower()
        results[step.profile_name][step.command] = {
            "result": {"y": "passed", "n": "failed"}.get(answer, "skipped")
        }
    if len(profiles) == 1:
        payload = {"profile": profiles[0].name, "commands": results[profiles[0].name]}
    else:
        payload = {"profiles": results}
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Validation written to {args.output}")
    return (
        0
        if all(
            item["result"] not in {"failed", "error"}
            for profile_results in results.values()
            for item in profile_results.values()
        )
        else 2
    )


def _discover_profiles(args: argparse.Namespace) -> list[Path] | None:
    if getattr(args, "profile", None):
        return args.profile
    profiles_dir: Path = getattr(args, "profiles_dir", Path("profiles"))
    if profiles_dir.is_dir():
        discovered = sorted(
            path
            for path in profiles_dir.glob("*.yaml")
            if not path.name.endswith(".observations.yaml")
        )
        if discovered:
            print(f"Using every profile in {profiles_dir}/:")
            for path in discovered:
                print(f"  {path}")
            return discovered
    fallback = Path("device-profile.yaml")
    if fallback.exists():
        return [fallback]
    return None


def _profile_paths(args: argparse.Namespace) -> list[Path]:
    profiles = _discover_profiles(args)
    if profiles is None:
        raise CeilingFanError(
            "No device profiles found. Pass --profile, or keep learned profiles in "
            f"{getattr(args, 'profiles_dir', Path('profiles'))}/."
        )
    return profiles


def _warn_profile_labels(profile_paths: list[Path]) -> None:
    for path in profile_paths:
        profile = DeviceProfile.load(path)
        if profile.protocol is not None:
            continue
        for warning in label_entity_warnings(profile.command_names()):
            print(f"warning: {path}: {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "doctor":
            profiles = _discover_profiles(args) if args.phase == "firmware" else None
            return cmd_doctor(args.phase, profiles)
        if args.phase == "learn" and args.action == "listen":
            return cmd_listen(args)
        if args.phase == "learn" and args.action == "prepare":
            return cmd_prepare_learning(args)
        if args.phase == "learn" and args.action == "inspire-pro":
            return cmd_inspire_pro(args)
        if args.phase == "learn" and args.action == "cjoy":
            return cmd_cjoy(args)
        if args.phase == "learn" and args.action in {"wizard", "raw"}:
            return cmd_raw(args)
        if args.phase == "research" and args.action == "scan":
            return cmd_scan(args)
        if args.phase == "research" and args.action == "capture":
            return cmd_capture(args)
        if args.phase == "research" and args.action == "analyze":
            return cmd_analyze(args)
        if args.phase == "firmware" and args.action == "build":
            profiles = _profile_paths(args)
            _warn_profile_labels(profiles)
            if args.web_ui:
                ensure_web_password(args.output.parent / "secrets.yaml")
            hostname = write_firmware(
                profiles, args.output, bridge_name=args.bridge_name, web_ui=args.web_ui
            )
            print(f"Firmware written to {args.output}")
            print(
                "Next: ceilingfan firmware deploy --device <current bridge "
                f"hostname>; afterwards it comes back as {hostname}.local."
            )
            return 0
        if args.phase == "hardware" and args.action == "onboard":
            return cmd_onboard(args)
        if args.phase == "firmware" and args.action == "deploy":
            profiles = _profile_paths(args)
            _warn_profile_labels(profiles)
            if args.web_ui:
                ensure_web_password(args.output.parent / "secrets.yaml")
            hostname = write_firmware(
                profiles, args.output, bridge_name=args.bridge_name, web_ui=args.web_ui
            )
            run_esphome(args.output, args.device)
            print(f"\nDeployed. The bridge is now reachable as {hostname}.local.")
            if args.web_ui:
                print(
                    f"Phone/browser control page: http://{hostname}.local "
                    f"(user admin, web_password in {args.output.parent / 'secrets.yaml'})."
                )
            print(
                "Next: validate every entity against its physical fan with: "
                f"ceilingfan firmware validate --device {hostname}.local"
            )
            return 0
        if args.phase == "firmware" and args.action == "validate":
            return cmd_validate(args)
        if args.phase == "control":
            return cmd_control(args)
        parser.error(f"Unknown command: {args.phase} {args.action}")
    except CeilingFanError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "error": str(exc)}))
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"error: external command failed with exit code {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    return 0
