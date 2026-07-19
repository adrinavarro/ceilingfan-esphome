from __future__ import annotations

from pathlib import Path

import pytest

from ceilingfan_esphome.bridge_learning import BridgeObservation, save_bridge_evidence
from ceilingfan_esphome.cli import (
    _profile_output_path,
    _profile_paths,
    build_parser,
    cmd_doctor,
    cmd_raw,
    main,
)
from ceilingfan_esphome.models import CeilingFanError


def test_cli_separates_normal_workflow_from_optional_research() -> None:
    parser = build_parser()

    hardware = parser.parse_args(["hardware", "onboard", "--port", "/dev/ttyUSB0"])
    firmware = parser.parse_args(
        ["firmware", "deploy", "--device", "ceilingfan-learning.local"]
    )
    research = parser.parse_args(
        ["research", "capture", "fan_off", "--frequency", "433.92M"]
    )

    assert (hardware.phase, hardware.action) == ("hardware", "onboard")
    assert (firmware.phase, firmware.action) == ("firmware", "deploy")
    assert (research.phase, research.action) == ("research", "capture")

    with pytest.raises(SystemExit):
        parser.parse_args(["learn", "capture", "fan_off", "--frequency", "433.92M"])


def test_firmware_build_accepts_multiple_profiles() -> None:
    parser = build_parser()

    firmware = parser.parse_args(
        [
            "firmware",
            "build",
            "--profile",
            "bedroom.yaml",
            "--profile",
            "office.yaml",
            "--bridge-name",
            "Home RF bridge",
        ]
    )

    assert firmware.profile == [Path("bedroom.yaml"), Path("office.yaml")]
    assert firmware.bridge_name == "Home RF bridge"


def test_firmware_doctor_accepts_multiple_profiles() -> None:
    parser = build_parser()

    firmware = parser.parse_args(
        [
            "firmware",
            "doctor",
            "--profile",
            "bedroom.yaml",
            "--profile",
            "office.yaml",
        ]
    )

    assert firmware.profile == [Path("bedroom.yaml"), Path("office.yaml")]


def test_learning_mode_can_be_installed_over_ota() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["learn", "prepare", "--device", "home-rf-bridge.local"]
    )

    assert (args.phase, args.action) == ("learn", "prepare")
    assert args.device == "home-rf-bridge.local"


def test_control_cli_exposes_list_and_entity_commands() -> None:
    parser = build_parser()

    listed = parser.parse_args(
        ["control", "list", "--device", "home-rf-bridge.local", "--json"]
    )
    fan = parser.parse_args(
        [
            "control",
            "fan",
            "--device",
            "home-rf-bridge.local",
            "--entity",
            "main_bedroom_fan",
            "--state",
            "on",
            "--speed",
            "4",
        ]
    )

    assert (listed.phase, listed.action, listed.json) == ("control", "list", True)
    assert (fan.phase, fan.action, fan.state, fan.speed) == (
        "control",
        "fan",
        "on",
        4,
    )


def test_learn_doctor_requires_esphome_not_rtl(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "firmware" / "learning.yaml"
    config.parent.mkdir()
    config.write_text("esphome:\n", encoding="utf-8")
    monkeypatch.setattr(
        "ceilingfan_esphome.cli.shutil.which",
        lambda name: "/usr/bin/esphome" if name == "esphome" else None,
    )

    result = cmd_doctor("learn")

    assert result == 0
    output = capsys.readouterr().out
    assert "esphome" in output
    assert "rtl_sdr" not in output
    assert "learn phase is ready" in output


def test_research_doctor_checks_optional_rtl_tools(monkeypatch, capsys) -> None:
    rtl_tools = {"rtl_sdr", "rtl_power", "rtl_test"}
    monkeypatch.setattr(
        "ceilingfan_esphome.cli.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in rtl_tools else None,
    )

    result = cmd_doctor("research")

    assert result == 0
    output = capsys.readouterr().out
    assert "rtl_sdr" in output
    assert "research phase is ready" in output


def test_learn_exposes_bridge_listener_and_inspire_pro_generator() -> None:
    parser = build_parser()

    listen = parser.parse_args(["learn", "listen", "--device", "ceilingfan.local"])
    profile = parser.parse_args(
        [
            "learn",
            "inspire-pro",
            "--remote-id",
            "0x080ED61",
            "--name",
            "Bedroom fan",
        ]
    )

    assert (listen.phase, listen.action, listen.device) == (
        "learn",
        "listen",
        "ceilingfan.local",
    )
    assert profile.remote_id == 0x080ED61


def test_learn_exposes_cjoy_profile_generator() -> None:
    parser = build_parser()

    profile = parser.parse_args(
        [
            "learn",
            "cjoy",
            "--remote-id",
            "0x175D0310",
            "--name",
            "CJOY bedroom",
        ]
    )

    assert (profile.phase, profile.action) == ("learn", "cjoy")
    assert profile.remote_id == 0x175D0310


def test_learn_exposes_generic_bridge_raw_workflow() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "learn",
            "wizard",
            "--command",
            "sleep_timer",
            "--name",
            "Nashi bedroom",
            "--attempts",
            "2",
            "--resume",
            "--output",
            "profiles/nashi.yaml",
        ]
    )

    assert (args.phase, args.action) == ("learn", "wizard")
    assert args.command == ["sleep_timer"]
    assert args.attempts == 2
    assert args.resume is True
    assert args.output == Path("profiles/nashi.yaml")


def test_raw_learning_resume_rebuilds_a_complete_profile_without_esphome(
    tmp_path: Path,
) -> None:
    parser = build_parser()
    evidence = tmp_path / "fan.observations.yaml"
    output = tmp_path / "fan.yaml"
    save_bridge_evidence(
        evidence,
        "Other fan",
        {
            "fan_toggle": [
                BridgeObservation(
                    frequency_hz=433_920_000,
                    preamble_us=[],
                    frame_us=[300, -700, 700, -300, 300],
                    gap_us=9_000,
                    repetitions=6,
                )
            ]
        },
    )
    args = parser.parse_args(
        [
            "learn",
            "raw",
            "--name",
            "Other fan",
            "--command",
            "fan_toggle",
            "--resume",
            "--evidence",
            str(evidence),
            "--output",
            str(output),
        ]
    )

    assert cmd_raw(args) == 0
    assert output.exists()


def test_hardware_doctor_does_not_require_rtl_tools(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "firmware" / "learning.yaml"
    config.parent.mkdir()
    config.write_text("esphome:\n", encoding="utf-8")
    monkeypatch.setattr(
        "ceilingfan_esphome.cli.shutil.which",
        lambda name: "/usr/bin/esphome" if name == "esphome" else None,
    )

    result = cmd_doctor("hardware")

    assert result == 0
    output = capsys.readouterr().out
    assert "rtl_sdr" not in output
    assert "hardware phase is ready" in output


def test_firmware_commands_discover_profiles_from_directory(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "bedroom.yaml").write_text("name: Bedroom\n", encoding="utf-8")
    (profiles / "bedroom.observations.yaml").write_text("evidence\n", encoding="utf-8")
    (profiles / "office.yaml").write_text("name: Office\n", encoding="utf-8")
    parser = build_parser()

    discovered = _profile_paths(parser.parse_args(["firmware", "build"]))
    explicit = _profile_paths(
        parser.parse_args(["firmware", "build", "--profile", "only.yaml"])
    )

    assert discovered == [Path("profiles/bedroom.yaml"), Path("profiles/office.yaml")]
    assert explicit == [Path("only.yaml")]
    assert "Using every profile in profiles/" in capsys.readouterr().out


def test_firmware_build_without_any_profiles_fails_with_guidance(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    parser = build_parser()

    with pytest.raises(CeilingFanError, match="No device profiles found"):
        _profile_paths(parser.parse_args(["firmware", "build"]))


def test_firmware_build_and_deploy_accept_web_ui() -> None:
    parser = build_parser()

    build = parser.parse_args(["firmware", "build", "--web-ui"])
    deploy = parser.parse_args(
        ["firmware", "deploy", "--device", "home-rf-bridge.local"]
    )

    assert build.web_ui is True
    assert deploy.web_ui is False


def test_profiles_default_into_the_profiles_directory() -> None:
    assert _profile_output_path("Main bedroom fan", None) == Path(
        "profiles/main-bedroom-fan.yaml"
    )
    assert _profile_output_path("Main bedroom fan", Path("custom.yaml")) == Path(
        "custom.yaml"
    )

    parser = build_parser()
    wizard = parser.parse_args(["learn", "wizard", "--name", "Bedroom fan"])
    assert wizard.output is None
    assert wizard.command is None
    assert wizard.verbose is False


def test_control_device_defaults_to_the_environment(monkeypatch) -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["control", "fan", "--entity", "bedroom_fan", "--state", "on"]
    )
    assert args.device is None

    monkeypatch.delenv("CEILINGFAN_DEVICE", raising=False)
    monkeypatch.delenv("CEILINGFAN_API_KEY", raising=False)
    result = main(["control", "fan", "--entity", "bedroom_fan", "--state", "on"])
    assert result == 2


def test_control_exposes_mdns_discovery() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["control", "discover", "--timeout", "2", "--all", "--json"]
    )

    assert (args.phase, args.action) == ("control", "discover")
    assert args.timeout == 2.0
    assert args.all is True
    assert args.json is True


def test_firmware_validate_accepts_a_device_for_automatic_triggering() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["firmware", "validate", "--device", "home-rf-bridge.local"]
    )

    assert args.device == "home-rf-bridge.local"
    assert args.port == 6053
    assert parser.parse_args(["firmware", "validate"]).device is None


def test_control_errors_are_json_when_requested(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    import json

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CEILINGFAN_API_KEY", raising=False)

    result = main(["control", "list", "--device", "bridge.local", "--json"])

    assert result == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "error"
    assert "secrets" in payload["error"]
    assert "error:" in captured.err


def test_research_doctor_reports_missing_numpy(monkeypatch, capsys) -> None:
    rtl_tools = {"rtl_sdr", "rtl_power", "rtl_test"}
    monkeypatch.setattr(
        "ceilingfan_esphome.cli.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in rtl_tools else None,
    )
    monkeypatch.setattr(
        "ceilingfan_esphome.cli.importlib.util.find_spec", lambda name: None
    )

    result = cmd_doctor("research")

    assert result == 1
    output = capsys.readouterr().out
    assert "numpy" in output
    assert "uv sync --extra research" in output


def test_research_commands_explain_missing_numpy(monkeypatch) -> None:
    def missing_numpy(name, package=None):
        raise ModuleNotFoundError("No module named 'numpy'", name="numpy")

    monkeypatch.setattr(
        "ceilingfan_esphome.cli.importlib.import_module", missing_numpy
    )
    parser = build_parser()
    args = parser.parse_args(
        ["research", "capture", "fan_off", "--frequency", "433.92M"]
    )

    with pytest.raises(CeilingFanError, match="uv sync --extra research"):
        from ceilingfan_esphome.cli import cmd_capture

        cmd_capture(args)
