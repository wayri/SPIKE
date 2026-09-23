"""Bounded extension registry and deterministic four-quadrant references."""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from .device_contracts import DeviceDescriptor, DeviceExtensionManifest


class DeviceExtensionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RegistryLimits:
    max_extensions: int = 64
    max_devices: int = 1024
    max_devices_per_extension: int = 128
    max_ports_per_device: int = 64
    max_variables_per_device: int = 512

    def __post_init__(self) -> None:
        for name in (
            "max_extensions", "max_devices", "max_devices_per_extension",
            "max_ports_per_device", "max_variables_per_device",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")


class DeviceExtensionRegistry:
    """Validates and indexes metadata; it deliberately cannot load code."""

    def __init__(self, host_capabilities: Iterable[str], limits: RegistryLimits | None = None):
        self._host_capabilities = frozenset(host_capabilities)
        self._limits = limits or RegistryLimits()
        self._extensions: dict[str, DeviceExtensionManifest] = {}
        self._devices: dict[str, DeviceDescriptor] = {}

    @property
    def extensions(self) -> Mapping[str, DeviceExtensionManifest]:
        return MappingProxyType(dict(self._extensions))

    @property
    def devices(self) -> Mapping[str, DeviceDescriptor]:
        return MappingProxyType(dict(self._devices))

    def register(
        self, manifest: DeviceExtensionManifest, devices: Iterable[DeviceDescriptor]
    ) -> None:
        descriptors = tuple(devices)
        if manifest.extension_id in self._extensions:
            raise DeviceExtensionError(f"Extension already registered: {manifest.extension_id}.")
        if len(self._extensions) >= self._limits.max_extensions:
            raise DeviceExtensionError("Extension registry limit reached.")
        if len(descriptors) > self._limits.max_devices_per_extension:
            raise DeviceExtensionError("Per-extension device limit exceeded.")
        if len(self._devices) + len(descriptors) > self._limits.max_devices:
            raise DeviceExtensionError("Device registry limit reached.")
        ids = tuple(device.device_id for device in descriptors)
        if ids != manifest.device_ids:
            raise DeviceExtensionError("Manifest device IDs must exactly match descriptor order.")
        if len(ids) != len(set(ids)) or any(device_id in self._devices for device_id in ids):
            raise DeviceExtensionError("Duplicate device ID.")
        missing = set(manifest.required_host_capabilities) - self._host_capabilities
        if missing:
            raise DeviceExtensionError(f"Host lacks capabilities: {', '.join(sorted(missing))}.")
        if not manifest.provenance.native_execution_trusted:
            raise DeviceExtensionError("Untrusted native extension registration is forbidden.")
        for device in descriptors:
            if device.runtime != manifest.provenance:
                raise DeviceExtensionError("Device runtime provenance must match its extension manifest.")
            if not device.runtime.native_execution_trusted:
                raise DeviceExtensionError("Untrusted native device registration is forbidden.")
            if len(device.electrical_terminals) + len(device.power_ports) > self._limits.max_ports_per_device:
                raise DeviceExtensionError(f"Device {device.device_id} exceeds the port limit.")
            if len(device.variables) > self._limits.max_variables_per_device:
                raise DeviceExtensionError(f"Device {device.device_id} exceeds the variable limit.")
            missing = set(device.solver.capabilities) - self._host_capabilities
            if missing:
                raise DeviceExtensionError(
                    f"Host lacks capabilities for {device.device_id}: {', '.join(sorted(missing))}."
                )
        self._extensions[manifest.extension_id] = manifest
        self._devices.update((device.device_id, device) for device in descriptors)


@dataclass(frozen=True, slots=True)
class IVEvaluation:
    voltage_v: float
    current_a: float
    conductance_s: float
    absorbed_power_w: float
    quadrant: str


def _quadrant(voltage: float, current: float) -> str:
    if voltage == 0.0 or current == 0.0:
        return "axis"
    if voltage > 0.0:
        return "I" if current > 0.0 else "IV"
    return "II" if current > 0.0 else "III"


def _evaluation(voltage: float, current: float, conductance: float) -> IVEvaluation:
    values = (voltage, current, conductance)
    if not all(math.isfinite(value) for value in values):
        raise DeviceExtensionError("I/V evaluation produced a non-finite result.")
    return IVEvaluation(voltage, current, conductance, voltage * current, _quadrant(voltage, current))


class TableIVDevice:
    """Piecewise-linear signed I(V), including active and NDR segments."""

    def __init__(self, points: Iterable[tuple[float, float]], *, ndr_allowed: bool):
        normalized = tuple((float(v), float(i)) for v, i in points)
        if len(normalized) < 2 or not all(math.isfinite(x) for point in normalized for x in point):
            raise DeviceExtensionError("I/V tables require at least two finite points.")
        voltages = tuple(point[0] for point in normalized)
        if any(right <= left for left, right in zip(voltages, voltages[1:])):
            raise DeviceExtensionError("I/V table voltages must be strictly increasing.")
        slopes = tuple(
            (right[1] - left[1]) / (right[0] - left[0])
            for left, right in zip(normalized, normalized[1:])
        )
        if not ndr_allowed and any(slope < 0.0 for slope in slopes):
            raise DeviceExtensionError("Negative differential resistance must be explicitly allowed.")
        self._points = normalized
        self._voltages = voltages
        self._slopes = slopes

    @property
    def voltage_range(self) -> tuple[float, float]:
        return self._voltages[0], self._voltages[-1]

    def evaluate(self, voltage_v: float) -> IVEvaluation:
        voltage = float(voltage_v)
        if not math.isfinite(voltage):
            raise DeviceExtensionError("Voltage must be finite.")
        if voltage < self._voltages[0] or voltage > self._voltages[-1]:
            raise DeviceExtensionError("Voltage is outside the table validity range.")
        index = min(max(bisect.bisect_right(self._voltages, voltage) - 1, 0), len(self._slopes) - 1)
        v0, i0 = self._points[index]
        slope = self._slopes[index]
        return _evaluation(voltage, i0 + slope * (voltage - v0), slope)


class PolynomialIVDevice:
    """Analytic signed I(V) reference with exact small-signal Jacobian."""

    def __init__(
        self,
        coefficients: Iterable[float],
        voltage_range: tuple[float, float],
        *,
        ndr_allowed: bool,
    ):
        coefficients = tuple(float(value) for value in coefficients)
        minimum, maximum = (float(value) for value in voltage_range)
        if not coefficients or not all(math.isfinite(value) for value in coefficients):
            raise DeviceExtensionError("Polynomial coefficients must be finite and non-empty.")
        if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum >= maximum:
            raise DeviceExtensionError("Polynomial voltage range is invalid.")
        # Conservatively sample derivative because a general root finder is outside this reference.
        if not ndr_allowed:
            for index in range(257):
                voltage = minimum + (maximum - minimum) * index / 256.0
                if self._derivative(coefficients, voltage) < 0.0:
                    raise DeviceExtensionError("Negative differential resistance must be explicitly allowed.")
        self._coefficients = coefficients
        self._voltage_range = (minimum, maximum)

    @staticmethod
    def _derivative(coefficients: tuple[float, ...], voltage: float) -> float:
        result = 0.0
        for order in range(len(coefficients) - 1, 0, -1):
            result = result * voltage + order * coefficients[order]
        return result

    def evaluate(self, voltage_v: float) -> IVEvaluation:
        voltage = float(voltage_v)
        if not math.isfinite(voltage):
            raise DeviceExtensionError("Voltage must be finite.")
        if voltage < self._voltage_range[0] or voltage > self._voltage_range[1]:
            raise DeviceExtensionError("Voltage is outside the analytic validity range.")
        current = 0.0
        for coefficient in reversed(self._coefficients):
            current = current * voltage + coefficient
        return _evaluation(voltage, current, self._derivative(self._coefficients, voltage))


__all__ = [
    "DeviceExtensionError", "DeviceExtensionRegistry", "IVEvaluation", "PolynomialIVDevice",
    "RegistryLimits", "TableIVDevice",
]
