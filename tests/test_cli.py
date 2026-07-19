from __future__ import annotations

from pathlib import Path

from ceilingfan_esphome.cli import build_parser, cmd_doctor


def test_cli_has_three_independent_phases() -> None:
    parser = build_parser()

    learn = parser.parse_args(["learn", "capture", "fan_off", "--frequency", "433.92M"])
    hardware = parser.parse_args(["hardware", "onboard", "--port", "/dev/ttyUSB0"])
    firmware = parser.parse_args(
        ["firmware", "deploy", "--device", "ceilingfan-onboarding.local"]
    )

    assert (learn.phase, learn.action) == ("learn", "capture")
    assert (hardware.phase, hardware.action) == ("hardware", "onboard")
    assert (firmware.phase, firmware.action) == ("firmware", "deploy")


def test_learn_doctor_does_not_require_esphome(monkeypatch, capsys) -> None:
    rtl_tools = {"rtl_sdr", "rtl_power", "rtl_test"}
    monkeypatch.setattr(
        "ceilingfan_esphome.cli.shutil.which",
        lambda name: f"/usr/bin/{name}" if name in rtl_tools else None,
    )

    result = cmd_doctor("learn")

    assert result == 0
    output = capsys.readouterr().out
    assert "esphome" not in output
    assert "learn phase is ready" in output


def test_hardware_doctor_does_not_require_rtl_tools(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "firmware" / "onboarding.yaml"
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
