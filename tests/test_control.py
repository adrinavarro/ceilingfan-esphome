from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from aioesphomeapi import ButtonInfo, ColorMode, FanInfo, LightInfo

from ceilingfan_esphome.control import (
    control_device,
    inspect_device,
    load_api_key,
    resolve_device,
    resolve_entity,
)
from ceilingfan_esphome.models import CeilingFanError


class FakeClient:
    def __init__(self, entities: list[Any]) -> None:
        self.entities = entities
        self.connected = False
        self.disconnected = False
        self.commands: list[tuple[str, int, dict[str, Any]]] = []

    async def connect(self, login: bool = False) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def list_entities_services(self) -> tuple[list[Any], list[Any]]:
        return self.entities, []

    def fan_command(self, key: int, **kwargs: Any) -> None:
        self.commands.append(("fan", key, kwargs))

    def light_command(self, key: int, **kwargs: Any) -> None:
        self.commands.append(("light", key, kwargs))

    def button_command(self, key: int, **kwargs: Any) -> None:
        self.commands.append(("button", key, kwargs))


def entities() -> list[Any]:
    return [
        FanInfo(
            object_id="main_bedroom_fan",
            key=11,
            name="Main bedroom fan",
            supported_speed_count=6,
        ),
        LightInfo(
            object_id="main_bedroom_light",
            key=12,
            name="Main bedroom fan light",
            supported_color_modes=[ColorMode.BRIGHTNESS],
        ),
        ButtonInfo(
            object_id="office_fan_dimmer_up",
            key=13,
            name="Office fan dimmer up",
        ),
    ]


def test_load_api_key_prefers_environment(tmp_path: Path) -> None:
    secrets = tmp_path / "missing.yaml"

    assert load_api_key(secrets, {"CEILINGFAN_API_KEY": "from-environment"}) == (
        "from-environment"
    )


def test_load_api_key_reads_esphome_secrets(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text("api_encryption_key: encrypted-local-key\n", encoding="utf-8")

    assert load_api_key(secrets, {}) == "encrypted-local-key"


def test_resolve_device_prefers_explicit_then_environment() -> None:
    assert resolve_device("bridge.local", {}) == "bridge.local"
    assert (
        resolve_device(None, {"CEILINGFAN_DEVICE": "home-rf-bridge.local"})
        == "home-rf-bridge.local"
    )
    with pytest.raises(CeilingFanError, match="control discover"):
        resolve_device(None, {})


def test_resolve_entity_accepts_object_id_or_exact_name() -> None:
    available = entities()

    assert resolve_entity(available, "fan", "main_bedroom_fan").key == 11
    assert resolve_entity(available, "fan", "MAIN BEDROOM FAN").key == 11


def test_inspect_device_lists_only_supported_entities() -> None:
    client = FakeClient(entities())

    result = asyncio.run(
        inspect_device(
            "home-rf-bridge.local",
            6053,
            "key",
            client_factory=lambda *_: client,
        )
    )

    assert [entity.type for entity in result] == ["fan", "light", "button"]
    assert result[0].speed_count == 6
    assert result[1].supports_brightness is True
    assert client.connected is True
    assert client.disconnected is True


def test_control_device_sends_fan_speed_through_native_entity() -> None:
    client = FakeClient(entities())

    result = asyncio.run(
        control_device(
            "home-rf-bridge.local",
            6053,
            "key",
            "fan",
            "main_bedroom_fan",
            state=True,
            speed=4,
            client_factory=lambda *_: client,
        )
    )

    assert result.command == {"state": "on", "speed": 4}
    assert result.to_dict()["status"] == "sent"
    assert result.to_dict()["acknowledged"] is False
    assert client.commands == [
        ("fan", 11, {"state": True, "speed_level": 4, "device_id": 0})
    ]
    assert client.disconnected is True


def test_control_device_rejects_out_of_range_speed_without_sending() -> None:
    client = FakeClient(entities())

    with pytest.raises(CeilingFanError, match="speeds 1-6"):
        asyncio.run(
            control_device(
                "home-rf-bridge.local",
                6053,
                "key",
                "fan",
                "main_bedroom_fan",
                state=True,
                speed=7,
                client_factory=lambda *_: client,
            )
        )

    assert client.commands == []
    assert client.disconnected is True


def test_control_device_presses_relative_command_button() -> None:
    client = FakeClient(entities())

    result = asyncio.run(
        control_device(
            "home-rf-bridge.local",
            6053,
            "key",
            "button",
            "office_fan_dimmer_up",
            client_factory=lambda *_: client,
        )
    )

    assert result.command == {"press": True}
    assert client.commands == [("button", 13, {"device_id": 0})]
