from __future__ import annotations

import argparse
import getpass
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .analysis import learn_profile
from .esphome import create_secrets, require_command, run_esphome, write_firmware
from .models import CeilingFanError
from .sigmf import write_metadata


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ceilingfan",
        description="Learn and deploy a local RF ceiling fan bridge.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    phases = parser.add_subparsers(dest="phase", required=True)

    learn = phases.add_parser(
        "learn", help="Discover and learn a remote using only an RTL-SDR."
    )
    learn_commands = learn.add_subparsers(dest="action", required=True)
    learn_commands.add_parser("doctor", help="Check RTL-SDR learning tools.")

    scan = learn_commands.add_parser("scan", help="Scan a frequency range with rtl_power.")
    scan.add_argument("--start", type=_frequency, default=420_000_000)
    scan.add_argument("--end", type=_frequency, default=450_000_000)
    scan.add_argument("--bin", type=_frequency, default=10_000)
    scan.add_argument("--duration", default="30s")
    scan.add_argument("--output", type=Path, default=Path("captures/scan.csv"))

    capture = learn_commands.add_parser("capture", help="Record one labeled remote command.")
    capture.add_argument("label", help="Semantic label, for example fan_speed_1.")
    capture.add_argument("--frequency", type=_frequency, required=True)
    capture.add_argument("--sample-rate", type=_frequency, default=1_024_000)
    capture.add_argument("--gain", type=float, default=20.0)
    capture.add_argument("--duration", type=_positive_float, default=4.0)
    capture.add_argument("--attempt", type=int, default=1)
    capture.add_argument("--directory", type=Path, default=Path("captures"))

    analyze = learn_commands.add_parser(
        "analyze", help="Learn static OOK waveforms from captures."
    )
    analyze.add_argument("--captures", type=Path, default=Path("captures"))
    analyze.add_argument("--name", required=True, help="Friendly device name.")
    analyze.add_argument("--output", type=Path, default=Path("device-profile.yaml"))

    hardware = phases.add_parser(
        "hardware", help="Prepare the assembled ESP32 and CC1101 using only USB."
    )
    hardware_commands = hardware.add_subparsers(dest="action", required=True)
    hardware_commands.add_parser("doctor", help="Check ESPHome and onboarding files.")
    onboard = hardware_commands.add_parser(
        "onboard", help="Create secrets and flash initial firmware over USB."
    )
    onboard.add_argument("--port", required=True, help="Serial port, such as /dev/ttyUSB0.")
    onboard.add_argument("--config", type=Path, default=Path("firmware/onboarding.yaml"))
    onboard.add_argument("--secrets", type=Path, default=Path("firmware/secrets.yaml"))

    firmware = phases.add_parser(
        "firmware", help="Generate, deploy, and validate final firmware over the network."
    )
    firmware_commands = firmware.add_subparsers(dest="action", required=True)
    firmware_commands.add_parser("doctor", help="Check ESPHome and learned profile files.")

    build = firmware_commands.add_parser(
        "build", help="Generate ESPHome firmware from a profile."
    )
    build.add_argument("--profile", type=Path, default=Path("device-profile.yaml"))
    build.add_argument("--output", type=Path, default=Path("firmware/generated.yaml"))

    deploy = firmware_commands.add_parser(
        "deploy", help="Build and install learned firmware over OTA."
    )
    deploy.add_argument("--profile", type=Path, default=Path("device-profile.yaml"))
    deploy.add_argument("--output", type=Path, default=Path("firmware/generated.yaml"))
    deploy.add_argument("--device", required=True, help="Device hostname or IP address.")

    validate = firmware_commands.add_parser(
        "validate", help="Record physical validation for each learned command."
    )
    validate.add_argument("--profile", type=Path, default=Path("device-profile.yaml"))
    validate.add_argument("--output", type=Path, default=Path("validation.json"))
    return parser


def cmd_doctor(phase: str) -> int:
    required_commands = {
        "learn": ("rtl_sdr", "rtl_power", "rtl_test"),
        "hardware": ("esphome",),
        "firmware": ("esphome",),
    }[phase]
    checks = {name: shutil.which(name) for name in required_commands}
    failed = False
    print(f"Checking the {phase} phase. No other phase hardware is required.\n")
    for name, path in checks.items():
        status = path or "MISSING"
        print(f"{name:12} {status}")
        failed |= path is None
    required_files = {
        "learn": (),
        "hardware": (Path("firmware/onboarding.yaml"),),
        "firmware": (Path("device-profile.yaml"), Path("firmware/secrets.yaml")),
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
    meta_path = write_metadata(
        data_path,
        label=args.label,
        sample_rate=args.sample_rate,
        frequency_hz=args.frequency,
        gain_db=args.gain,
    )
    print(f"Capture written to {data_path} and {meta_path}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    paths = sorted(args.captures.glob("*.sigmf-meta"))
    profile = learn_profile(paths, args.name)
    profile.save(args.output)
    print(f"Learned {len(profile.commands)} commands and wrote {args.output}")
    for label, command in sorted(profile.commands.items()):
        print(
            f"  {label}: {command.repetitions} repetitions, "
            f"confidence {command.confidence:.1%}"
        )
    return 0


def cmd_onboard(args: argparse.Namespace) -> int:
    if args.secrets.exists():
        answer = input(f"{args.secrets} already exists. Replace it? [y/N] ").strip().lower()
        if answer != "y":
            raise CeilingFanError("Onboarding cancelled")
    ssid = input("Wi-Fi SSID: ").strip()
    wifi_password = getpass.getpass("Wi-Fi password: ")
    if not ssid or not wifi_password:
        raise CeilingFanError("Wi-Fi SSID and password are required")
    create_secrets(args.secrets, ssid, wifi_password)
    run_esphome(args.config, args.port)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from .models import DeviceProfile

    profile = DeviceProfile.load(args.profile)
    results = {}
    print("Trigger each command from Home Assistant, then record the physical result.")
    for command in sorted(profile.commands):
        answer = input(f"Did '{command}' work correctly? [y/n/s] ").strip().lower()
        results[command] = {"result": {"y": "passed", "n": "failed"}.get(answer, "skipped")}
    args.output.write_text(json.dumps({"profile": profile.name, "commands": results}, indent=2) + "\n")
    print(f"Validation written to {args.output}")
    return 0 if all(item["result"] != "failed" for item in results.values()) else 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "doctor":
            return cmd_doctor(args.phase)
        if args.phase == "learn" and args.action == "scan":
            return cmd_scan(args)
        if args.phase == "learn" and args.action == "capture":
            return cmd_capture(args)
        if args.phase == "learn" and args.action == "analyze":
            return cmd_analyze(args)
        if args.phase == "firmware" and args.action == "build":
            write_firmware(args.profile, args.output)
            print(f"Firmware written to {args.output}")
            return 0
        if args.phase == "hardware" and args.action == "onboard":
            return cmd_onboard(args)
        if args.phase == "firmware" and args.action == "deploy":
            write_firmware(args.profile, args.output)
            run_esphome(args.output, args.device)
            return 0
        if args.phase == "firmware" and args.action == "validate":
            return cmd_validate(args)
        parser.error(f"Unknown command: {args.phase} {args.action}")
    except CeilingFanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"error: external command failed with exit code {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    return 0
