# SPDX-License-Identifier: Apache-2.0
"""Inert, versioned settings for firmware-controlled owned electrical pads.

This module performs no firmware or native-library work.  Values describe a
generic user-supplied pad model; they are not manufacturer-characterized data.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import math
import re

from python.spikes.native_io_pad import PadProfile, PadState
from .firmware_image import TARGETS
from .firmware_session import gpio_pin


SETTINGS_VERSION = 1
QUALIFICATION = "generic_unqualified"
GENERIC_WARNING = (
    "Generic, unqualified electrical pad model. Values are user-supplied and do "
    "not represent manufacturer limits, register fidelity, SI/PI qualification, "
    "or hardware validation. Static overrides affect only the circuit pad state; "
    "they do not write or reinterpret firmware registers."
)

PROFILE_FIELDS = tuple(PadProfile.__dataclass_fields__)
BOOL_PROFILE_FIELDS = ("enable_clamp_to_vdd", "enable_clamp_to_vss")
RESISTANCE_FIELDS = (
    "high_strong_resistance_ohm", "high_weak_resistance_ohm",
    "low_strong_resistance_ohm", "low_weak_resistance_ohm",
    "pull_up_resistance_ohm", "pull_down_resistance_ohm", "off_resistance_ohm",
)
NONNEGATIVE_FIELDS = (
    "package_resistance_ohm", "package_inductance_h",
    "capacitance_to_vss_f", "capacitance_to_vdd_f",
)
POSITIVE_FIELDS = (
    "clamp_saturation_current_a", "clamp_emission_coefficient",
    "clamp_temperature_k",
)

_SOURCES = ("firmware", "static")
_MODES = ("input", "push_pull", "open_drain", "open_source")
_OUTPUTS = ("low", "high", "released")
_DRIVE_LEVELS = ("strong", "weak")
_PULLS = ("none", "up", "down")


def gpio_pins(board):
    """Return physical header pins with an unambiguous admitted MCU GPIO."""
    if not isinstance(board, dict) or board.get("id") not in TARGETS:
        raise ValueError("Electrical pads require an admitted native firmware board")
    if not isinstance(board.get("pins"), (list, tuple)):
        raise ValueError("Controller board pins are required")
    result = []
    for pin in board["pins"]:
        try:
            port, index = gpio_pin(board["id"], pin)
        except ValueError:
            continue
        result.append((pin, port, index))
    return tuple(result)


def _default_pin():
    return {
        "enabled": False,
        "signal_node": "",
        "vdd_node": "",
        "vss_node": "0",
        "output_source": "firmware",
        "pull_source": "firmware",
        "static_state": asdict(PadState()),
        "profile": asdict(PadProfile()),
        "vil_ratio": .3,
        "vih_ratio": .7,
    }


def default_settings(board):
    """Create a JSON-compatible per-board settings snapshot."""
    pins = {pin["id"]: _default_pin() for pin, _port, _index in gpio_pins(board)}
    return {
        "version": SETTINGS_VERSION,
        "board_id": board["id"],
        "qualification": QUALIFICATION,
        "pins": pins,
    }


def _finite_number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + " must be a finite number")
    return float(value)


def _single_line(value, label, *, required):
    if not isinstance(value, str) or "\0" in value or "\r" in value or "\n" in value:
        raise ValueError(label + " must be a single-line name")
    value = value.strip()
    if required and not value:
        raise ValueError(label + " is required for an enabled pad")
    return value


def _validate_static_state(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " static_state must be an object")
    if set(value) != {"mode", "output", "drive_level", "pull"}:
        raise ValueError(label + " static_state fields do not match version 1")
    mode, output = value["mode"], value["output"]
    if mode not in _MODES or output not in _OUTPUTS:
        raise ValueError(label + " has an unknown static output state")
    if value["drive_level"] not in _DRIVE_LEVELS or value["pull"] not in _PULLS:
        raise ValueError(label + " has an unknown static drive or pull state")
    allowed = {
        "input": ("released",), "push_pull": ("low", "high"),
        "open_drain": ("low", "released"),
        "open_source": ("high", "released"),
    }
    if output not in allowed[mode]:
        raise ValueError(label + " static mode/output combination is invalid")
    return {key: value[key] for key in ("mode", "output", "drive_level", "pull")}


def _validate_profile(value, label):
    if not isinstance(value, dict) or set(value) != set(PROFILE_FIELDS):
        raise ValueError(label + " profile fields do not match owned PadProfile")
    result = {}
    for name in PROFILE_FIELDS:
        item = value[name]
        if name in BOOL_PROFILE_FIELDS:
            if type(item) is not bool:
                raise ValueError(label + " " + name + " must be boolean")
            result[name] = item
        else:
            result[name] = _finite_number(item, label + " " + name)
    for name in RESISTANCE_FIELDS:
        if not 1e-6 <= result[name] <= 1e15:
            raise ValueError(label + " " + name + " must be within [1e-6, 1e15] ohm")
    for name in NONNEGATIVE_FIELDS:
        if result[name] < 0 or (name == "package_resistance_ohm" and 0 < result[name] < 1e-6):
            raise ValueError(label + " " + name + " must be zero or within its finite native range")
    if result['package_resistance_ohm']>1e15:
        raise ValueError(label+' package resistance must not exceed 1e15 ohm')
    for name in POSITIVE_FIELDS:
        if result[name] <= 0:
            raise ValueError(label + " " + name + " must be finite and positive")
    if result["high_weak_resistance_ohm"] < result["high_strong_resistance_ohm"]:
        raise ValueError(label + " weak high-drive resistance must not be below strong drive")
    if result["low_weak_resistance_ohm"] < result["low_strong_resistance_ohm"]:
        raise ValueError(label + " weak low-drive resistance must not be below strong drive")
    active = [result[name] for name in RESISTANCE_FIELDS if name != "off_resistance_ohm"]
    if result["off_resistance_ohm"] < max(active):
        raise ValueError(label + " off resistance must not be below drive or pull resistance")
    return result


def validate_settings(settings, board):
    """Validate and return a detached, canonical version-1 snapshot."""
    if not isinstance(settings, dict):
        raise ValueError("Electrical pad settings must be an object")
    if settings.get("version") != SETTINGS_VERSION:
        raise ValueError("Unsupported electrical pad settings version")
    if settings.get("board_id") != board.get("id"):
        raise ValueError("Electrical pad settings belong to a different board")
    if settings.get("qualification") != QUALIFICATION:
        raise ValueError("Electrical pad qualification must remain generic/unqualified")
    values = settings.get("pins")
    admitted = {pin["id"]: (pin, port, index) for pin, port, index in gpio_pins(board)}
    if not isinstance(values, dict) or set(values) != set(admitted):
        raise ValueError("Electrical pad settings must cover exactly the mapped physical GPIO pins")
    result = default_settings(board)
    enabled_gpio = set()
    for pin_id, raw in values.items():
        label = admitted[pin_id][0]["label"]
        if not isinstance(raw, dict):
            raise ValueError(label + " settings must be an object")
        expected = set(_default_pin())
        if set(raw) != expected:
            raise ValueError(label + " settings fields do not match version 1")
        enabled = raw["enabled"]
        if type(enabled) is not bool:
            raise ValueError(label + " enabled must be boolean")
        pin = result["pins"][pin_id]
        pin["enabled"] = enabled
        pin["signal_node"] = _single_line(raw["signal_node"], label + " signal node", required=enabled)
        pin["vdd_node"] = _single_line(raw["vdd_node"], label + " VDD node", required=enabled)
        pin["vss_node"] = _single_line(raw["vss_node"], label + " VSS node", required=enabled)
        for name in ("output_source", "pull_source"):
            if raw[name] not in _SOURCES:
                raise ValueError(label + " " + name + " must be firmware or static")
            pin[name] = raw[name]
        pin["static_state"] = _validate_static_state(raw["static_state"], label)
        pin["profile"] = _validate_profile(raw["profile"], label)
        pin["vil_ratio"] = _finite_number(raw["vil_ratio"], label + " VIL ratio")
        pin["vih_ratio"] = _finite_number(raw["vih_ratio"], label + " VIH ratio")
        if not 0 <= pin["vil_ratio"] < pin["vih_ratio"] <= 1:
            raise ValueError(label + " requires 0 <= VIL/VDD < VIH/VDD <= 1")
        if enabled:
            gpio = admitted[pin_id][1:]
            if gpio in enabled_gpio:
                raise ValueError("Only one physical header pin may bind MCU GPIO P%s.%s" % gpio)
            enabled_gpio.add(gpio)
    return deepcopy(result)


def enabled_connections(settings, board):
    """Build explicit PadConnections without executing or inspecting firmware."""
    from .firmware_electrical import PadConnection
    settings = validate_settings(settings, board)
    admitted = {pin["id"]: (port, index) for pin, port, index in gpio_pins(board)}
    result = []
    for pin_id, value in settings["pins"].items():
        if not value["enabled"]:
            continue
        port, index = admitted[pin_id]
        prefix = "firmware_pad_" + re.sub(r"[^A-Za-z0-9_]", "_", pin_id)
        result.append(PadConnection(prefix, str(port), index, value["signal_node"],
                                    value["vdd_node"], value["vss_node"],
                                    PadProfile(**value["profile"]),
                                    value["vil_ratio"], value["vih_ratio"]))
    return tuple(result)


def settings_by_prefix(settings, board):
    """Return detached enabled-pin settings keyed like ``connections()``."""
    normalized = validate_settings(settings, board)
    enabled = [value for value in normalized["pins"].values() if value["enabled"]]
    return {connection.prefix: value
            for connection, value in zip(enabled_connections(normalized, board), enabled)}


def resolve_pad_state(pin_settings, firmware_state):
    """Apply explicit output/pull overrides to a decoded firmware PadState.

    This changes only the circuit state.  It neither modifies registers nor
    claims that a static selection came from the executing firmware.
    """
    if isinstance(firmware_state, dict):
        firmware_state = PadState(**firmware_state)
    if not isinstance(firmware_state, PadState):
        raise TypeError("Expected decoded firmware PadState")
    if pin_settings.get("output_source") not in _SOURCES or pin_settings.get("pull_source") not in _SOURCES:
        raise ValueError("Pad state sources must be firmware or static")
    static = PadState(**_validate_static_state(pin_settings["static_state"], "pad"))
    output = firmware_state if pin_settings["output_source"] == "firmware" else static
    pull = firmware_state.pull if pin_settings["pull_source"] == "firmware" else static.pull
    return PadState(output.mode, output.output, output.drive_level, pull)


# Short integration-facing names.  The descriptive originals remain useful in
# call sites where more than one settings contract is in scope.
validate = validate_settings
connections = enabled_connections
