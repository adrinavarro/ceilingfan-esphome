from __future__ import annotations

import json
import re
import secrets
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .models import CeilingFanError, DeviceProfile, LearnedWaveform
from .protocols import (
    CJOY_HEADER,
    CJOY_ONE,
    CJOY_REPETITIONS,
    CJOY_WAKE,
    CJOY_ZERO,
    SOMFY_COMMANDS,
    SOMFY_FIRST_HW_SYNC,
    SOMFY_HW_SYNC_US,
    SOMFY_INTERFRAME_US,
    SOMFY_KEY,
    SOMFY_REPEAT_FRAMES,
    SOMFY_REPEAT_HW_SYNC,
    SOMFY_SW_SYNC_US,
    SOMFY_SYMBOL_US,
    SOMFY_WAKEUP_US,
    cjoy_tail,
)


def command_waveform(command: LearnedWaveform) -> list[int]:
    waveform: list[int] = []

    def append(duration: int) -> None:
        if not duration:
            return
        # Same-sign neighbors merge: consecutive marks extend each other, while
        # overlapping spaces (a frame's trailing space followed by the repeat
        # gap) keep only the longer silence instead of stacking both.
        if waveform and (waveform[-1] > 0) == (duration > 0):
            if duration < 0:
                waveform[-1] = -max(abs(waveform[-1]), abs(duration))
            else:
                waveform[-1] += duration
            return
        waveform.append(duration)

    if command.preamble_us:
        for duration in command.preamble_us:
            append(duration)
        append(-command.gap_us)
    for repetition in range(command.repetitions):
        for duration in command.frame_us:
            append(duration)
        if repetition + 1 < command.repetitions:
            append(-command.gap_us)
    if not waveform:
        raise CeilingFanError("Cannot generate an empty RF waveform")
    if waveform[0] < 0:
        waveform.pop(0)
    if waveform[-1] > 0:
        append(-command.trailing_space_us)
    if len(waveform) % 2:
        raise CeilingFanError("Generated waveform does not contain mark/space pairs")
    return waveform


# Internal YAML ids only. ESPHome's own object_id sanitize rule differs
# (it keeps hyphens and repeated separators), so never use this to predict
# a deployed entity's object_id — select entities by exact name instead.
def _identifier(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return result or "ceiling_fan"


def hostname_slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "ceiling-fan"


_PLAIN_YAML_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _\-]*[A-Za-z0-9_\-]|[A-Za-z0-9]")


def _yaml_scalar(value: str) -> str:
    """Quote free-form text (names) so `#`, `:`, quotes, etc. survive YAML."""
    if _PLAIN_YAML_TEXT.fullmatch(value):
        return value
    return json.dumps(value)


def bridge_hostname(
    profiles: Sequence[DeviceProfile], bridge_name: str | None = None
) -> str:
    if bridge_name is None:
        bridge_name = profiles[0].name if len(profiles) == 1 else "Ceiling fan bridge"
    return hostname_slug(bridge_name)


_SPEED_LABEL = re.compile(r"fan_speed_(\d+)")
_BRIGHTNESS_LABEL = re.compile(r"light_brightness_(\d+)")

# Somfy cover controls exposed as stateless buttons, in validation press order.
# Friendly labels are shared by render_firmware and validation_steps so the
# generated entity names stay identical (guarded by tests/test_esphome.py).
SOMFY_BUTTONS = (
    ("cover_up", "up"),
    ("cover_my", "stop"),
    ("cover_down", "down"),
    ("cover_prog", "pairing"),
)


def label_entity_warnings(labels: Sequence[str]) -> list[str]:
    """Explain which absolute entities these command labels will (not) create.

    The firmware generator silently exposes unrecognized labels as stateless
    buttons, so a mislabeled command degrades without an error. These warnings
    let the wizard and the firmware commands surface that before deployment.
    """
    present = set(labels)
    warnings: list[str] = []
    for label in sorted(present):
        match = re.fullmatch(r"(fan_speed|light_brightness)(\d+)", label)
        if match:
            warnings.append(
                f"'{label}' looks like a typo of '{match.group(1)}_{match.group(2)}' "
                "and would become a stateless button."
            )
    speeds = sorted(
        int(match.group(1)) for label in present if (match := _SPEED_LABEL.fullmatch(label))
    )
    if speeds and "fan_off" not in present:
        warnings.append(
            "fan_speed_N without fan_off: no fan entity will be created; "
            "these commands become stateless buttons."
        )
    elif "fan_off" in present and not speeds:
        warnings.append(
            "fan_off without any fan_speed_N: no fan entity will be created; "
            "fan_off becomes a stateless button."
        )
    elif speeds and speeds != list(range(1, max(speeds) + 1)):
        missing = sorted(set(range(1, max(speeds) + 1)) - set(speeds))
        warnings.append(
            "fan speeds are not contiguous from 1 (missing "
            + ", ".join(str(speed) for speed in missing)
            + "); the missing speeds fall back to the lowest learned speed."
        )
    brightness = sorted(
        int(match.group(1))
        for label in present
        if (match := _BRIGHTNESS_LABEL.fullmatch(label))
    )
    if brightness and (
        "light_off" not in present or brightness != list(range(1, max(brightness) + 1))
    ):
        warnings.append(
            "light_brightness_N needs light_off plus contiguous levels starting "
            "at 1; firmware generation will fail otherwise."
        )
    if "light_on" in present and "light_off" not in present:
        warnings.append(
            "light_on without light_off: no light entity will be created; "
            "light_on becomes a stateless button."
        )
    return warnings


def _profile_ids(profiles: Sequence[DeviceProfile]) -> list[str]:
    profile_ids = [_identifier(profile.name) for profile in profiles]
    duplicates = sorted(
        profile_id for profile_id in set(profile_ids) if profile_ids.count(profile_id) > 1
    )
    if duplicates:
        raise CeilingFanError(
            "Fan names must produce unique identifiers. Rename the profiles that map to: "
            + ", ".join(duplicates)
        )
    return profile_ids


def render_firmware(
    profile: DeviceProfile | Sequence[DeviceProfile],
    bridge_name: str | None = None,
    web_ui: bool = False,
) -> str:
    profiles = [profile] if isinstance(profile, DeviceProfile) else list(profile)
    if not profiles:
        raise CeilingFanError("At least one device profile is required")

    modulations = {item.modulation for item in profiles}
    if len(modulations) > 1:
        raise CeilingFanError(
            "All profiles on one CC1101 must use the same modulation type"
        )
    for item in profiles:
        if not 300_000_000 <= item.frequency_hz <= 928_000_000:
            raise CeilingFanError(
                f"Profile '{item.name}' frequency must be between 300MHz and 928MHz"
            )
        if not -30 <= item.output_power_dbm <= 11:
            raise CeilingFanError(
                f"Profile '{item.name}' output power must be between -30dBm and 11dBm"
            )
        if item.protocol is not None:
            family = item.protocol.family
            if family == "cjoy":
                if not 0 <= item.protocol.remote_id < (1 << 32):
                    raise CeilingFanError(
                        f"Profile '{item.name}' CJOY remote ID must be a 32-bit value"
                    )
                if "fan_off" not in item.protocol.commands:
                    raise CeilingFanError(
                        f"Profile '{item.name}' CJOY protocol must define fan_off"
                    )
                if any(
                    not 0 <= code < (1 << 6)
                    for code in item.protocol.commands.values()
                ):
                    raise CeilingFanError(
                        f"Profile '{item.name}' CJOY commands must be 6-bit values"
                    )
            elif family == "somfy_rts":
                if not 0 <= item.protocol.remote_id < (1 << 24):
                    raise CeilingFanError(
                        f"Profile '{item.name}' Somfy remote address must be 24-bit"
                    )
                if not {"cover_up", "cover_down"} <= set(item.protocol.commands):
                    raise CeilingFanError(
                        f"Profile '{item.name}' Somfy protocol must define cover_up "
                        "and cover_down"
                    )
                if any(
                    code not in set(SOMFY_COMMANDS.values())
                    for code in item.protocol.commands.values()
                ):
                    raise CeilingFanError(
                        f"Profile '{item.name}' has unknown Somfy command nibbles"
                    )
            else:
                raise CeilingFanError(
                    f"Profile '{item.name}' uses unsupported protocol family "
                    f"'{family}'"
                )

    profile_ids = _profile_ids(profiles)
    if bridge_name is None:
        bridge_name = profiles[0].name if len(profiles) == 1 else "Ceiling fan bridge"
    device_id = bridge_hostname(profiles, bridge_name)
    # Wi-Fi SSIDs are limited to 32 bytes. The suffix occupies nine ASCII bytes.
    fallback_ssid = f"{device_id[:23].rstrip('-')} fallback"

    arrays: list[str] = []
    cases: list[str] = []
    globals_entries: list[str] = []
    fan_entries: list[str] = []
    output_entries: list[str] = []
    light_entries: list[str] = []
    button_entries: list[str] = []
    command_index = 0
    multi_profile = len(profiles) > 1
    has_cjoy = any(
        item.protocol is not None and item.protocol.family == "cjoy"
        for item in profiles
    )
    has_somfy = any(
        item.protocol is not None and item.protocol.family == "somfy_rts"
        for item in profiles
    )
    for current_profile, profile_id in zip(profiles, profile_ids, strict=True):
        command_names = current_profile.command_names()
        command_ids: dict[str, int] = {}
        claimed_commands: set[str] = set()
        cjoy_phase_id = None
        somfy_code_id = None
        sync_command_ids: list[int] = []
        if current_profile.protocol is None:
            for name in command_names:
                command_ids[name] = command_index
                values = command_waveform(current_profile.commands[name])
                array_prefix = f"{profile_id}_" if multi_profile else ""
                array_name = f"wave_{array_prefix}{_identifier(name)}"
                formatted = ", ".join(str(value) for value in values)
                arrays.append(
                    f"          static const int32_t {array_name}[] = {{{formatted}}};"
                )
                cases.append(
                    f"            case {command_index}: waveform = {array_name}; "
                    f"length = sizeof({array_name}) / sizeof({array_name}[0]); break;"
                )
                command_index += 1
        elif current_profile.protocol.family == "somfy_rts":
            protocol = current_profile.protocol
            somfy_code_id = (
                f"{profile_id}_somfy_code" if multi_profile else "somfy_code"
            )
            globals_entries.append(
                f"""  - id: {somfy_code_id}
    type: uint16_t
    restore_value: yes
    initial_value: '1'
"""
            )
            for name in command_names:
                cmd_nibble = protocol.commands[name]
                command_ids[name] = command_index
                cases.append(
                    f"""            case {command_index}: {{
              const uint16_t rolling = id({somfy_code_id});
              build_somfy(0x{protocol.remote_id:06X}, 0x{cmd_nibble:02X}, rolling);
              id({somfy_code_id}) = rolling + 1;
              waveform = dynamic_waveform.data();
              length = dynamic_waveform.size();
              break;
            }}"""
                )
                command_index += 1
        else:
            protocol = current_profile.protocol
            cjoy_phase_id = (
                f"{profile_id}_cjoy_phase" if multi_profile else "cjoy_phase"
            )
            globals_entries.append(
                f"""  - id: {cjoy_phase_id}
    type: uint8_t
    restore_value: yes
    initial_value: '0'
"""
            )
            for name in command_names:
                code = protocol.commands[name]
                command_ids[name] = command_index
                tails = ", ".join(f"0x{cjoy_tail(code, phase):03X}" for phase in range(4))
                cases.append(
                    f"""            case {command_index}: {{
              static const uint16_t tails[4] = {{{tails}}};
              const uint8_t phase = id({cjoy_phase_id}) & 0x03;
              build_cjoy(0x{protocol.remote_id:08X}, 0x{code:02X}, tails[phase]);
              id({cjoy_phase_id}) = (phase + 1) & 0x03;
              waveform = dynamic_waveform.data();
              length = dynamic_waveform.size();
              break;
            }}"""
                )
                command_index += 1

            off_code = protocol.commands["fan_off"]
            for phase in range(4):
                sync_command_ids.append(command_index)
                cases.append(
                    f"""            case {command_index}: {{
              build_cjoy(0x{protocol.remote_id:08X}, 0x{off_code:02X}, 0x{cjoy_tail(off_code, phase):03X});
              id({cjoy_phase_id}) = {(phase + 1) & 0x03};
              waveform = dynamic_waveform.data();
              length = dynamic_waveform.size();
              break;
            }}"""
                )
                command_index += 1

        speed_keys = sorted(
            (
                (int(match.group(1)), key)
                for key in command_names
                if (match := re.fullmatch(r"fan_speed_(\d+)", key))
            ),
            key=lambda item: item[0],
        )
        brightness_keys = sorted(
            (
                (int(match.group(1)), key)
                for key in command_names
                if (match := re.fullmatch(r"light_brightness_(\d+)", key))
            ),
            key=lambda item: item[0],
        )
        if brightness_keys:
            brightness_levels = [level for level, _ in brightness_keys]
            expected_levels = list(range(1, max(brightness_levels) + 1))
            if brightness_levels != expected_levels or "light_off" not in command_ids:
                raise CeilingFanError(
                    f"Profile '{current_profile.name}' must define light_off and "
                    "contiguous light_brightness_N commands starting at 1"
                )
        frequency = current_profile.frequency_hz
        output_power = current_profile.output_power_dbm
        fan_id = f"{profile_id}_fan" if multi_profile else "ceiling_fan"
        light_output_id = (
            f"{profile_id}_light_output" if multi_profile else "ceiling_light_output"
        )
        light_id = f"{profile_id}_light" if multi_profile else "ceiling_light"
        fan_name = current_profile.name if multi_profile else "Ceiling fan"
        light_name = (
            f"{current_profile.name} light" if multi_profile else "Ceiling fan light"
        )

        if "fan_off" in command_ids and speed_keys:
            speed_cases = "\n".join(
                f"                case {speed}: return {command_ids[key]};"
                for speed, key in speed_keys
            )
            fan_entries.append(
                f"""  - platform: template
    id: {fan_id}
    name: {_yaml_scalar(fan_name)}
    speed_count: {max(speed for speed, _ in speed_keys)}
    restore_mode: RESTORE_DEFAULT_OFF
    on_state:
      then:
        - script.execute:
            id: transmit_command
            frequency: {frequency}
            output_power: {output_power}
            command: !lambda |-
              if (!x->state) return {command_ids['fan_off']};
              switch (x->speed) {{
{speed_cases}
                default: return {command_ids[speed_keys[0][1]]};
              }}
"""
            )
            claimed_commands.add("fan_off")
            claimed_commands.update(key for _, key in speed_keys)
        if brightness_keys:
            max_brightness = max(level for level, _ in brightness_keys)
            brightness_cases = "\n".join(
                f"              case {level}: return {command_ids[key]};"
                for level, key in brightness_keys
            )
            output_entries.append(
                f"""  - platform: template
    id: {light_output_id}
    type: float
    write_action:
      - script.execute:
          id: transmit_command
          frequency: {frequency}
          output_power: {output_power}
          command: !lambda |-
            if (state <= 0.0f) return {command_ids['light_off']};
            int level = static_cast<int>(state * {max_brightness} + 0.5f);
            if (level < 1) level = 1;
            if (level > {max_brightness}) level = {max_brightness};
            switch (level) {{
{brightness_cases}
              default: return {command_ids[brightness_keys[-1][1]]};
            }}
"""
            )
            light_entries.append(
                f"""  - platform: monochromatic
    id: {light_id}
    name: {_yaml_scalar(light_name)}
    output: {light_output_id}
    gamma_correct: 1.0
    default_transition_length: 0s
    restore_mode: RESTORE_DEFAULT_OFF
"""
            )
            claimed_commands.add("light_off")
            claimed_commands.update(key for _, key in brightness_keys)
        elif "light_on" in command_ids and "light_off" in command_ids:
            output_entries.append(
                f"""  - platform: template
    id: {light_output_id}
    type: binary
    write_action:
      - script.execute:
          id: transmit_command
          frequency: {frequency}
          output_power: {output_power}
          command: !lambda |-
            return state ? {command_ids['light_on']} : {command_ids['light_off']};
"""
            )
            light_entries.append(
                f"""  - platform: binary
    id: {light_id}
    name: {_yaml_scalar(light_name)}
    output: {light_output_id}
    restore_mode: RESTORE_DEFAULT_OFF
"""
            )
            claimed_commands.update(("light_on", "light_off"))
        if (
            current_profile.protocol is not None
            and current_profile.protocol.family == "somfy_rts"
        ):
            # Somfy is a rolling-code cover: each command is a stateless button so
            # the CLI, web UI, and Home Assistant can all drive it today. A native
            # cover entity is the natural next slice once control.py speaks cover.
            for label, friendly_label in SOMFY_BUTTONS:
                if label not in command_ids:
                    continue
                button_id = (
                    f"{profile_id}_{label}" if multi_profile else f"somfy_{label}"
                )
                button_entries.append(
                    f"""  - platform: template
    id: {button_id}
    name: {_yaml_scalar(f'{current_profile.name} {friendly_label}')}
    on_press:
      - script.execute:
          id: transmit_command
          frequency: {frequency}
          output_power: {output_power}
          command: {command_ids[label]}
"""
                )
        elif current_profile.protocol is not None:
            relative_buttons = (
                ("light_toggle", "light toggle"),
                ("dimmer_down", "dimmer down"),
                ("dimmer_up", "dimmer up"),
            )
            for label, friendly_label in relative_buttons:
                if label not in command_ids:
                    continue
                button_id = (
                    f"{profile_id}_{label}" if multi_profile else f"cjoy_{label}"
                )
                button_name = (
                    f"{current_profile.name} {friendly_label}"
                    if multi_profile
                    else f"CJOY {friendly_label}"
                )
                button_entries.append(
                    f"""  - platform: template
    id: {button_id}
    name: {_yaml_scalar(button_name)}
    on_press:
      - script.execute:
          id: transmit_command
          frequency: {frequency}
          output_power: {output_power}
          command: {command_ids[label]}
"""
                )
            sync_id = (
                f"{profile_id}_cjoy_sync" if multi_profile else "cjoy_sync"
            )
            sync_name = (
                f"{current_profile.name} synchronize RF phase"
                if multi_profile
                else "CJOY synchronize RF phase"
            )
            sync_actions = "\n".join(
                f"""      - script.execute:
          id: transmit_command
          frequency: {frequency}
          output_power: {output_power}
          command: {sync_command_id}"""
                for sync_command_id in sync_command_ids
            )
            button_entries.append(
                f"""  - platform: template
    id: {sync_id}
    name: {_yaml_scalar(sync_name)}
    icon: mdi:sync
    on_press:
{sync_actions}
"""
            )
        else:
            # Static raw profiles may contain relative controls or commands whose
            # state semantics are not known. Expose every command not claimed by
            # an absolute fan/light entity as a stateless button.
            for label in command_names:
                if label in claimed_commands:
                    continue
                friendly_label = label.replace("_", " ")
                button_id = (
                    f"{profile_id}_{_identifier(label)}"
                    if multi_profile
                    else f"raw_{_identifier(label)}"
                )
                button_entries.append(
                    f"""  - platform: template
    id: {button_id}
    name: {_yaml_scalar(f'{current_profile.name} {friendly_label}')}
    on_press:
      - script.execute:
          id: transmit_command
          frequency: {frequency}
          output_power: {output_power}
          command: {command_ids[label]}
"""
                )
    if not fan_entries and not light_entries and not button_entries:
        raise CeilingFanError(
            "No supported entities found. Label commands as fan_off/fan_speed_N "
            "or use light_off with light_on or contiguous light_brightness_N commands."
        )

    array_block = "\n".join(arrays)
    case_block = "\n".join(cases)
    globals_section = (
        "globals:\n" + "\n".join(globals_entries) if globals_entries else ""
    )
    dynamic_builders = ""
    if has_cjoy or has_somfy:
        dynamic_builders += "          std::vector<int32_t> dynamic_waveform;\n"
    if has_cjoy:
        dynamic_builders += f"""          const auto build_cjoy = [&](uint32_t remote_id, uint8_t code, uint16_t tail) {{
            dynamic_waveform.clear();
            dynamic_waveform.reserve(502);
            const auto append_pair = [&](int32_t mark, int32_t space) {{
              dynamic_waveform.push_back(mark);
              dynamic_waveform.push_back(-space);
            }};
            append_pair({CJOY_WAKE[0]}, {CJOY_WAKE[1]});
            const uint64_t frame = (static_cast<uint64_t>(remote_id) << 17) |
                                   (static_cast<uint64_t>(code) << 11) | tail;
            for (int repetition = 0; repetition < {CJOY_REPETITIONS}; repetition++) {{
              append_pair({CJOY_HEADER[0]}, {CJOY_HEADER[1]});
              for (int bit = 48; bit >= 0; bit--) {{
                if ((frame >> bit) & 1ULL) {{
                  append_pair({CJOY_ONE[0]}, {CJOY_ONE[1]});
                }} else {{
                  append_pair({CJOY_ZERO[0]}, {CJOY_ZERO[1]});
                }}
              }}
            }}
          }};
"""
    if has_somfy:
        # Mirrors protocols.somfy_frame_bytes / somfy_waveform. Manchester
        # half-symbols of the same level coalesce into one pulse; the vector
        # holds signed marks(+)/spaces(-) like build_cjoy.
        dynamic_builders += f"""          const auto build_somfy = [&](uint32_t address, uint8_t command, uint16_t rolling_code) {{
            uint8_t frame[7];
            frame[0] = 0x{SOMFY_KEY:02X};
            frame[1] = (command & 0x0F) << 4;
            frame[2] = (rolling_code >> 8) & 0xFF;
            frame[3] = rolling_code & 0xFF;
            frame[4] = (address >> 16) & 0xFF;
            frame[5] = (address >> 8) & 0xFF;
            frame[6] = address & 0xFF;
            uint8_t checksum = 0;
            for (int i = 0; i < 7; i++) checksum ^= frame[i] ^ (frame[i] >> 4);
            frame[1] |= checksum & 0x0F;
            for (int i = 1; i < 7; i++) frame[i] ^= frame[i - 1];
            dynamic_waveform.clear();
            dynamic_waveform.reserve(700);
            bool current_mark = false;
            int32_t current_len = 0;
            const auto flush = [&]() {{
              if (current_len == 0) return;
              dynamic_waveform.push_back(current_mark ? current_len : -current_len);
              current_len = 0;
            }};
            const auto add = [&](bool mark, int32_t duration) {{
              if (current_len != 0 && mark == current_mark) {{ current_len += duration; return; }}
              flush();
              current_mark = mark;
              current_len = duration;
            }};
            const auto emit_frame = [&](int hw_sync, bool wakeup) {{
              if (wakeup) {{ add(true, {SOMFY_WAKEUP_US[0]}); add(false, {SOMFY_WAKEUP_US[1]}); }}
              for (int i = 0; i < hw_sync; i++) {{ add(true, {SOMFY_HW_SYNC_US}); add(false, {SOMFY_HW_SYNC_US}); }}
              add(true, {SOMFY_SW_SYNC_US[0]}); add(false, {SOMFY_SW_SYNC_US[1]});
              for (int i = 0; i < 56; i++) {{
                const uint8_t bit = (frame[i / 8] >> (7 - (i % 8))) & 1;
                if (bit) {{ add(false, {SOMFY_SYMBOL_US}); add(true, {SOMFY_SYMBOL_US}); }}
                else {{ add(true, {SOMFY_SYMBOL_US}); add(false, {SOMFY_SYMBOL_US}); }}
              }}
              add(false, {SOMFY_INTERFRAME_US});
            }};
            emit_frame({SOMFY_FIRST_HW_SYNC}, true);
            for (int r = 0; r < {SOMFY_REPEAT_FRAMES}; r++) emit_frame({SOMFY_REPEAT_HW_SYNC}, false);
            flush();
          }};
"""
    entity_sections = []
    if fan_entries:
        entity_sections.append("fan:\n" + "\n".join(fan_entries))
    if output_entries:
        entity_sections.append("output:\n" + "\n".join(output_entries))
    if light_entries:
        entity_sections.append("light:\n" + "\n".join(light_entries))
    if button_entries:
        entity_sections.append("button:\n" + "\n".join(button_entries))
    entities = "\n".join(entity_sections)
    # The web UI is HTTP with basic auth on the local network, unlike the
    # encrypted native API. It stays opt-in for phone/browser control without
    # Home Assistant.
    web_server_section = ""
    if web_ui:
        # Digest auth keeps the password out of the (still unencrypted) HTTP
        # traffic; ESPHome's current default is the reversible basic scheme.
        web_server_section = """
web_server:
  port: 80
  auth:
    type: digest
    username: admin
    password: !secret web_password
"""
    return f"""# Generated by ceilingfan-esphome. Edit the profile, not this file.
substitutions:
  device_name: {device_id}
  friendly_name: {_yaml_scalar(bridge_name)}
  fallback_ssid: {fallback_ssid}

esphome:
  name: ${{device_name}}
  friendly_name: ${{friendly_name}}
  min_version: 2025.12.0
  # Advertised over mDNS so `ceilingfan control discover` can find the bridge.
  project:
    name: adrinavarro.ceilingfan-esphome
    version: "{__version__}"

esp32:
  board: esp32dev
  framework:
    type: esp-idf

logger:

api:
  encryption:
    key: !secret api_encryption_key

ota:
  - platform: esphome
    password: !secret ota_password

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
    ssid: "${{fallback_ssid}}"
    password: !secret fallback_password

captive_portal:
{web_server_section}
spi:
  clk_pin: GPIO18
  mosi_pin: GPIO23
  miso_pin: GPIO19

cc1101:
  id: radio
  cs_pin: GPIO14
  frequency: {profiles[0].frequency_hz / 1_000_000:.5f}MHz
  modulation_type: {profiles[0].modulation}
  symbol_rate: 5000
  output_power: {profiles[0].output_power_dbm}

remote_transmitter:
  id: rf_transmitter
  pin: GPIO26
  carrier_duty_percent: 100%
  non_blocking: false
  on_transmit:
    then:
      - cc1101.begin_tx
  on_complete:
    then:
      - cc1101.set_idle

{globals_section}
script:
  - id: transmit_command
    mode: queued
    parameters:
      command: int
      frequency: float
      output_power: float
    then:
      - lambda: |-
          id(radio).set_idle();
          id(radio).set_output_power(output_power);
          id(radio).set_frequency(frequency);
          const int32_t *waveform = nullptr;
          size_t length = 0;
{array_block}
{dynamic_builders}
          switch (command) {{
{case_block}
            default:
              ESP_LOGE("ceilingfan_esphome", "Unknown command %d", command);
              return;
          }}
          auto call = id(rf_transmitter).transmit();
          auto *data = call.get_data();
          for (size_t i = 0; i < length; i += 2) {{
            data->item(waveform[i], -waveform[i + 1]);
          }}
          call.perform();

{entities}"""


@dataclass(frozen=True)
class ValidationStep:
    """One physical check: send this entity command, then ask what happened."""

    profile_name: str
    command: str
    entity_type: str
    entity_name: str
    state: bool | None = None
    speed: int | None = None
    brightness: float | None = None


def validation_steps(profiles: Sequence[DeviceProfile]) -> list[ValidationStep]:
    """Map each profile command to the generated entity that exercises it.

    Selects entities by their exact name (resolve_entity matches names
    case-insensitively), never by object_id: ESPHome derives object_ids with
    its own sanitize rule, which keeps hyphens and repeated separators, and
    reimplementing it here would drift. The consistency test in
    tests/test_esphome.py guards these names against render_firmware.
    """
    profiles = list(profiles)
    multi_profile = len(profiles) > 1
    steps: list[ValidationStep] = []
    for profile in profiles:
        command_names = profile.command_names()
        claimed: set[str] = set()
        fan_name = profile.name if multi_profile else "Ceiling fan"
        light_name = f"{profile.name} light" if multi_profile else "Ceiling fan light"
        speed_keys = sorted(
            (int(match.group(1)), key)
            for key in command_names
            if (match := _SPEED_LABEL.fullmatch(key))
        )
        brightness_keys = sorted(
            (int(match.group(1)), key)
            for key in command_names
            if (match := _BRIGHTNESS_LABEL.fullmatch(key))
        )
        if profile.protocol is not None and profile.protocol.family == "cjoy":
            # Synchronize the receiver's protocol phase before judging commands.
            sync_name = (
                f"{profile.name} synchronize RF phase"
                if multi_profile
                else "CJOY synchronize RF phase"
            )
            steps.append(
                ValidationStep(
                    profile_name=profile.name,
                    command="synchronize_rf_phase",
                    entity_type="button",
                    entity_name=sync_name,
                )
            )
        if "fan_off" in command_names and speed_keys:
            for speed, key in speed_keys:
                steps.append(
                    ValidationStep(
                        profile_name=profile.name,
                        command=key,
                        entity_type="fan",
                        entity_name=fan_name,
                        state=True,
                        speed=speed,
                    )
                )
            steps.append(
                ValidationStep(
                    profile_name=profile.name,
                    command="fan_off",
                    entity_type="fan",
                    entity_name=fan_name,
                    state=False,
                )
            )
            claimed.add("fan_off")
            claimed.update(key for _, key in speed_keys)
        if brightness_keys:
            max_brightness = max(level for level, _ in brightness_keys)
            for level, key in brightness_keys:
                steps.append(
                    ValidationStep(
                        profile_name=profile.name,
                        command=key,
                        entity_type="light",
                        entity_name=light_name,
                        state=True,
                        brightness=level / max_brightness,
                    )
                )
            steps.append(
                ValidationStep(
                    profile_name=profile.name,
                    command="light_off",
                    entity_type="light",
                    entity_name=light_name,
                    state=False,
                )
            )
            claimed.add("light_off")
            claimed.update(key for _, key in brightness_keys)
        elif "light_on" in command_names and "light_off" in command_names:
            steps.append(
                ValidationStep(
                    profile_name=profile.name,
                    command="light_on",
                    entity_type="light",
                    entity_name=light_name,
                    state=True,
                )
            )
            steps.append(
                ValidationStep(
                    profile_name=profile.name,
                    command="light_off",
                    entity_type="light",
                    entity_name=light_name,
                    state=False,
                )
            )
            claimed.update(("light_on", "light_off"))
        if profile.protocol is not None and profile.protocol.family == "somfy_rts":
            for label, friendly_label in SOMFY_BUTTONS:
                if label not in command_names:
                    continue
                steps.append(
                    ValidationStep(
                        profile_name=profile.name,
                        command=label,
                        entity_type="button",
                        entity_name=f"{profile.name} {friendly_label}",
                    )
                )
        elif profile.protocol is not None:
            relative_buttons = (
                ("light_toggle", "light toggle"),
                ("dimmer_down", "dimmer down"),
                ("dimmer_up", "dimmer up"),
            )
            for label, friendly_label in relative_buttons:
                if label not in command_names:
                    continue
                button_name = (
                    f"{profile.name} {friendly_label}"
                    if multi_profile
                    else f"CJOY {friendly_label}"
                )
                steps.append(
                    ValidationStep(
                        profile_name=profile.name,
                        command=label,
                        entity_type="button",
                        entity_name=button_name,
                    )
                )
        else:
            for label in command_names:
                if label in claimed:
                    continue
                friendly_label = label.replace("_", " ")
                steps.append(
                    ValidationStep(
                        profile_name=profile.name,
                        command=label,
                        entity_type="button",
                        entity_name=f"{profile.name} {friendly_label}",
                    )
                )
    return steps


def write_firmware(
    profile_path: Path | Sequence[Path],
    output_path: Path,
    bridge_name: str | None = None,
    web_ui: bool = False,
) -> str:
    """Render firmware for the profiles and return the bridge's mDNS hostname."""
    profile_paths = [profile_path] if isinstance(profile_path, Path) else list(profile_path)
    profiles = [DeviceProfile.load(path) for path in profile_paths]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_firmware(profiles, bridge_name=bridge_name, web_ui=web_ui),
        encoding="utf-8",
    )
    return bridge_hostname(profiles, bridge_name)


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        hint = (
            " Install it with: uv sync --extra firmware" if name == "esphome" else ""
        )
        raise CeilingFanError(f"Required command not found: {name}.{hint}")
    return path


def run_esphome(config: Path, device: str) -> None:
    executable = require_command("esphome")
    subprocess.run([executable, "run", str(config), "--device", device], check=True)


def run_esphome_logs(config: Path, device: str) -> None:
    executable = require_command("esphome")
    try:
        subprocess.run([executable, "logs", str(config), "--device", device], check=True)
    except KeyboardInterrupt:
        pass


def create_secrets(path: Path, ssid: str, wifi_password: str) -> None:
    import base64

    path.parent.mkdir(parents=True, exist_ok=True)
    api_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    import json

    content = (
        f"wifi_ssid: {json.dumps(ssid)}\n"
        f"wifi_password: {json.dumps(wifi_password)}\n"
        f'fallback_password: "{secrets.token_urlsafe(18)}"\n'
        f'api_encryption_key: "{api_key}"\n'
        f'ota_password: "{secrets.token_urlsafe(24)}"\n'
        f'web_password: "{secrets.token_urlsafe(18)}"\n'
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def ensure_web_password(path: Path) -> None:
    """Add web_password to a secrets file created before the web UI existed."""
    if not path.exists():
        raise CeilingFanError(
            f"ESPHome secrets not found at {path}. Run hardware onboarding first."
        )
    if "web_password:" in path.read_text(encoding="utf-8"):
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f'web_password: "{secrets.token_urlsafe(18)}"\n')
    print(f"Added a generated web_password to {path}")
