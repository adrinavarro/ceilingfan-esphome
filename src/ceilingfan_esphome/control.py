from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml
from aioesphomeapi import (
    APIClient,
    APIConnectionError,
    ButtonInfo,
    CoverInfo,
    EntityInfo,
    FanInfo,
    LightInfo,
)

from . import __version__
from .models import CeilingFanError

API_KEY_ENVIRONMENT_VARIABLE = "CEILINGFAN_API_KEY"
DEVICE_ENVIRONMENT_VARIABLE = "CEILINGFAN_DEVICE"

# The `project` metadata every generated firmware advertises over mDNS.
DISCOVERY_PROJECT_NAME = "adrinavarro.ceilingfan-esphome"
_ESPHOME_MDNS_SERVICE = "_esphomelib._tcp.local."


def resolve_device(
    device: str | None,
    environment: Mapping[str, str] | None = None,
) -> str:
    environment = os.environ if environment is None else environment
    if device:
        return device
    if value := environment.get(DEVICE_ENVIRONMENT_VARIABLE, "").strip():
        return value
    raise CeilingFanError(
        f"No bridge specified. Pass --device or set {DEVICE_ENVIRONMENT_VARIABLE}. "
        "Find bridges on the local network with: ceilingfan control discover"
    )


@dataclass(frozen=True)
class DiscoveredBridge:
    hostname: str
    address: str | None
    name: str
    project: str | None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def discover_bridges(
    timeout: float = 5.0, all_devices: bool = False
) -> list[DiscoveredBridge]:
    """Browse mDNS for ESPHome devices; keep only ceilingfan bridges by default.

    Bridges deployed before discovery metadata existed advertise no project
    name and only appear with all_devices=True (or after a redeploy).
    """
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ModuleNotFoundError as exc:  # pragma: no cover - zeroconf is a base dep
        raise CeilingFanError(
            "Discovery needs the zeroconf package; reinstall the CLI or use --device."
        ) from exc

    found: dict[str, DiscoveredBridge] = {}

    class _Listener(ServiceListener):
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if info is None:
                return
            properties = {
                key.decode("utf-8", "replace"): value.decode("utf-8", "replace")
                for key, value in (info.properties or {}).items()
                if value is not None
            }
            addresses = info.parsed_addresses()
            found[name] = DiscoveredBridge(
                hostname=(info.server or name).rstrip("."),
                address=addresses[0] if addresses else None,
                name=properties.get("friendly_name", name.split(".", 1)[0]),
                project=properties.get("project_name"),
            )

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            self.add_service(zc, type_, name)

        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

    zeroconf = Zeroconf()
    try:
        ServiceBrowser(zeroconf, _ESPHOME_MDNS_SERVICE, _Listener())
        time.sleep(timeout)
    finally:
        zeroconf.close()
    bridges = sorted(found.values(), key=lambda bridge: bridge.hostname)
    if all_devices:
        return bridges
    return [bridge for bridge in bridges if bridge.project == DISCOVERY_PROJECT_NAME]


class NativeAPIClient(Protocol):
    async def connect(self, login: bool = False) -> None: ...

    async def disconnect(self) -> None: ...

    async def list_entities_services(
        self,
    ) -> tuple[list[EntityInfo], list[Any]]: ...

    def fan_command(
        self,
        key: int,
        state: bool | None = None,
        speed_level: int | None = None,
        device_id: int = 0,
    ) -> None: ...

    def light_command(
        self,
        key: int,
        state: bool | None = None,
        brightness: float | None = None,
        device_id: int = 0,
    ) -> None: ...

    def button_command(self, key: int, device_id: int = 0) -> None: ...

    def cover_command(
        self,
        key: int,
        position: float | None = None,
        stop: bool = False,
        device_id: int = 0,
    ) -> None: ...


ClientFactory = Callable[[str, int, str], NativeAPIClient]


@dataclass(frozen=True)
class ControllableEntity:
    type: str
    name: str
    object_id: str
    speed_count: int | None = None
    supports_brightness: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class ControlResult:
    device: str
    entity: ControllableEntity
    command: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "sent",
            # These consumer RF protocols are one-way: "sent" proves the bridge
            # queued the transmission, never that the receiver acted on it.
            "acknowledged": False,
            "device": self.device,
            "entity": self.entity.to_dict(),
            "command": self.command,
        }


def load_api_key(
    secrets_path: Path,
    environment: Mapping[str, str] | None = None,
) -> str:
    environment = os.environ if environment is None else environment
    if key := environment.get(API_KEY_ENVIRONMENT_VARIABLE, "").strip():
        return key
    if not secrets_path.exists():
        raise CeilingFanError(
            f"ESPHome secrets not found at {secrets_path}. Run hardware onboarding or "
            f"set {API_KEY_ENVIRONMENT_VARIABLE}."
        )
    raw = yaml.safe_load(secrets_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CeilingFanError(f"Invalid ESPHome secrets file: {secrets_path}")
    key = raw.get("api_encryption_key")
    if not isinstance(key, str) or not key.strip():
        raise CeilingFanError(
            f"api_encryption_key is missing from {secrets_path}"
        )
    return key.strip()


def _default_client_factory(address: str, port: int, api_key: str) -> NativeAPIClient:
    return APIClient(
        address,
        port,
        "",
        client_info=f"ceilingfan-esphome/{__version__}",
        noise_psk=api_key,
        provide_time=False,
    )


def _entity_type(entity: EntityInfo) -> str | None:
    if isinstance(entity, FanInfo):
        return "fan"
    if isinstance(entity, LightInfo):
        return "light"
    if isinstance(entity, ButtonInfo):
        return "button"
    if isinstance(entity, CoverInfo):
        return "cover"
    return None


def _public_entity(entity: EntityInfo) -> ControllableEntity:
    entity_type = _entity_type(entity)
    if entity_type is None:
        raise CeilingFanError(f"Entity '{entity.name}' is not controllable")
    if isinstance(entity, FanInfo):
        return ControllableEntity(
            type=entity_type,
            name=entity.name,
            object_id=entity.object_id,
            speed_count=entity.supported_speed_count,
        )
    if isinstance(entity, LightInfo):
        supports_brightness = any(int(mode) != 1 for mode in entity.supported_color_modes)
        return ControllableEntity(
            type=entity_type,
            name=entity.name,
            object_id=entity.object_id,
            supports_brightness=supports_brightness,
        )
    return ControllableEntity(
        type=entity_type,
        name=entity.name,
        object_id=entity.object_id,
    )


def list_controllable_entities(entities: Sequence[EntityInfo]) -> list[ControllableEntity]:
    return [
        _public_entity(entity)
        for entity in entities
        if _entity_type(entity) is not None
    ]


def resolve_entity(
    entities: Sequence[EntityInfo], entity_type: str, selector: str
) -> EntityInfo:
    candidates = [entity for entity in entities if _entity_type(entity) == entity_type]
    exact_ids = [entity for entity in candidates if entity.object_id == selector]
    if len(exact_ids) == 1:
        return exact_ids[0]
    exact_names = [
        entity for entity in candidates if entity.name.casefold() == selector.casefold()
    ]
    if len(exact_names) == 1:
        return exact_names[0]
    if len(exact_names) > 1:
        raise CeilingFanError(
            f"Ambiguous {entity_type} name '{selector}'; use its object_id instead"
        )
    available = ", ".join(
        f"{entity.object_id} ({entity.name})" for entity in candidates
    )
    suffix = f" Available: {available}." if available else ""
    raise CeilingFanError(f"No {entity_type} entity matches '{selector}'.{suffix}")


async def inspect_device(
    device: str,
    port: int,
    api_key: str,
    *,
    client_factory: ClientFactory = _default_client_factory,
) -> list[ControllableEntity]:
    client = client_factory(device, port, api_key)
    try:
        await client.connect(login=True)
        entities, _ = await client.list_entities_services()
        return list_controllable_entities(entities)
    except APIConnectionError as exc:
        raise CeilingFanError(f"Could not connect securely to {device}:{port}: {exc}") from exc
    finally:
        await client.disconnect()


async def control_device(
    device: str,
    port: int,
    api_key: str,
    entity_type: str,
    selector: str,
    *,
    state: bool | None = None,
    speed: int | None = None,
    brightness: float | None = None,
    cover_action: str | None = None,
    client_factory: ClientFactory = _default_client_factory,
) -> ControlResult:
    client = client_factory(device, port, api_key)
    try:
        await client.connect(login=True)
        entities, _ = await client.list_entities_services()
        entity = resolve_entity(entities, entity_type, selector)
        command: dict[str, Any]
        if isinstance(entity, FanInfo):
            if state is None:
                raise CeilingFanError("A fan command requires an on/off state")
            if speed is not None and not 1 <= speed <= entity.supported_speed_count:
                raise CeilingFanError(
                    f"Fan '{entity.name}' accepts speeds 1-{entity.supported_speed_count}"
                )
            client.fan_command(
                entity.key,
                state=state,
                speed_level=speed,
                device_id=entity.device_id,
            )
            command = {"state": "on" if state else "off"}
            if speed is not None:
                command["speed"] = speed
        elif isinstance(entity, LightInfo):
            if state is None:
                raise CeilingFanError("A light command requires an on/off state")
            if brightness is not None and not 0.0 <= brightness <= 1.0:
                raise CeilingFanError("Light brightness must be between 0 and 1")
            if brightness is not None and not _public_entity(entity).supports_brightness:
                raise CeilingFanError(f"Light '{entity.name}' does not support brightness")
            client.light_command(
                entity.key,
                state=state,
                brightness=brightness,
                device_id=entity.device_id,
            )
            command = {"state": "on" if state else "off"}
            if brightness is not None:
                command["brightness"] = brightness
        elif isinstance(entity, CoverInfo):
            if cover_action not in {"open", "close", "stop"}:
                raise CeilingFanError(
                    "A cover command requires an action of open, close, or stop"
                )
            # An optimistic template cover maps position 1.0/0.0 to its
            # open/close actions; stop is a distinct command.
            if cover_action == "stop":
                client.cover_command(entity.key, stop=True, device_id=entity.device_id)
            else:
                client.cover_command(
                    entity.key,
                    position=1.0 if cover_action == "open" else 0.0,
                    device_id=entity.device_id,
                )
            command = {"action": cover_action}
        elif isinstance(entity, ButtonInfo):
            client.button_command(entity.key, device_id=entity.device_id)
            command = {"press": True}
        else:  # pragma: no cover - resolve_entity enforces the requested type
            raise CeilingFanError(f"Unsupported entity type: {entity_type}")
        return ControlResult(device, _public_entity(entity), command)
    except APIConnectionError as exc:
        raise CeilingFanError(f"Could not connect securely to {device}:{port}: {exc}") from exc
    finally:
        await client.disconnect()
