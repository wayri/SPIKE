"""Versioned contracts for extensible, multi-physics SPIKES devices.

The contracts in this module are metadata only.  In particular, an extension
manifest never causes Python, native, HDL, or WASM code to be loaded.  A future
runtime can consume qualified manifests without changing the model contract.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


DEVICE_CONTRACT = "spikes/device/v1"
DEVICE_EXTENSION_CONTRACT = "spikes/device-extension/v1"
RUNTIME_PROVENANCE_CONTRACT = "spikes/runtime-provenance/v1"

_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$", re.ASCII)
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

SUPPORTED_CAPABILITIES = frozenset({
    "dc_residual",
    "transient_residual",
    "analytic_jacobian",
    "numeric_jacobian",
    "jacobian_sparsity",
    "events",
    "discontinuous",
    "four_quadrant_iv",
    "negative_differential_resistance",
    "thermal_coupling",
    "rotational_coupling",
    "translational_coupling",
    "magnetic_coupling",
    "acoustic_coupling",
})

PORT_DOMAINS: Mapping[str, tuple[str, str, str, str]] = MappingProxyType({
    # Domain: effort name/unit, flow name/unit.  effort * flow is watts.
    "thermal": ("temperature", "K", "entropy_flow", "W/K"),
    "rotational": ("angular_velocity", "rad/s", "torque", "N*m"),
    "translational": ("velocity", "m/s", "force", "N"),
    "magnetic": ("flux_rate", "Wb/s", "magnetomotive_force", "A.turn"),
    "acoustic": ("pressure", "Pa", "volume_velocity", "m^3/s"),
})


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number.")
    return result


def _valid_id(value: str, label: str) -> None:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase ASCII identifier.")


def _unique_ids(values: tuple[Any, ...], label: str) -> None:
    ids = tuple(value.port_id if hasattr(value, "port_id") else value.name for value in values)
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} IDs must be unique.")


@dataclass(frozen=True, slots=True)
class ElectricalTerminal:
    """One MNA terminal; current is positive into the device."""

    port_id: str
    description: str = ""
    reference: bool = False

    def __post_init__(self) -> None:
        _valid_id(self.port_id, "Electrical terminal ID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.port_id,
            "domain": "electrical",
            "effort": {"name": "voltage", "unit": "V"},
            "flow": {"name": "current_into_device", "unit": "A"},
            "reference": self.reference,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class PowerPort:
    """A typed non-electrical, power-conserving effort/flow port."""

    port_id: str
    domain: str
    description: str = ""

    def __post_init__(self) -> None:
        _valid_id(self.port_id, "Power-port ID")
        if self.domain not in PORT_DOMAINS:
            raise ValueError(f"Unsupported power-port domain: {self.domain}.")

    @property
    def effort_name(self) -> str:
        return PORT_DOMAINS[self.domain][0]

    @property
    def effort_unit(self) -> str:
        return PORT_DOMAINS[self.domain][1]

    @property
    def flow_name(self) -> str:
        return PORT_DOMAINS[self.domain][2]

    @property
    def flow_unit(self) -> str:
        return PORT_DOMAINS[self.domain][3]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.port_id,
            "domain": self.domain,
            "effort": {"name": self.effort_name, "unit": self.effort_unit},
            "flow": {"name": self.flow_name, "unit": self.flow_unit},
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class DeviceVariable:
    name: str
    role: str
    unit: str
    default: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        _valid_id(self.name, "Variable name")
        if self.role not in {"parameter", "state", "observable"}:
            raise ValueError("Variable role must be parameter, state, or observable.")
        if not self.unit.strip():
            raise ValueError("Variables require an explicit unit or '1'.")
        default = _finite(self.default, self.name)
        minimum = None if self.minimum is None else _finite(self.minimum, f"{self.name}.minimum")
        maximum = None if self.maximum is None else _finite(self.maximum, f"{self.name}.maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"{self.name} minimum exceeds maximum.")
        if minimum is not None and default < minimum or maximum is not None and default > maximum:
            raise ValueError(f"{self.name} default is outside its bounds.")
        object.__setattr__(self, "default", default)
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "role": self.role, "unit": self.unit,
            "default": self.default, "minimum": self.minimum, "maximum": self.maximum,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ValidityBound:
    name: str
    unit: str
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        _valid_id(self.name, "Validity-bound name")
        if not self.unit.strip():
            raise ValueError("Validity bounds require an explicit unit.")
        minimum = _finite(self.minimum, f"{self.name}.minimum")
        maximum = _finite(self.maximum, f"{self.name}.maximum")
        if minimum >= maximum:
            raise ValueError("Validity minimum must be less than maximum.")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "unit": self.unit, "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True, slots=True)
class DeviceValidityEnvelope:
    bounds: tuple[ValidityBound, ...]
    outside_policy: str = "error"
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.bounds:
            raise ValueError("A device validity envelope cannot be empty.")
        _unique_ids(self.bounds, "Validity-bound")
        if self.outside_policy not in {"error", "warn"}:
            raise ValueError("Outside policy must be error or warn; implicit clamping is forbidden.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "bounds": [bound.to_dict() for bound in self.bounds],
            "outside_policy": self.outside_policy,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class SolverInterface:
    """Declares equations supplied by a device, never inferred promises."""

    capabilities: tuple[str, ...]
    residual_form: str
    jacobian: str
    state_equation: str = "none"

    def __post_init__(self) -> None:
        if not self.capabilities or len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("Solver capabilities must be non-empty and unique.")
        unsupported = set(self.capabilities) - SUPPORTED_CAPABILITIES
        if unsupported:
            raise ValueError(f"Unsupported solver capabilities: {', '.join(sorted(unsupported))}.")
        if self.residual_form not in {"explicit_current", "implicit_residual", "mna_stamp"}:
            raise ValueError("Unsupported residual form.")
        if self.jacobian not in {"analytic", "automatic_differentiation", "numeric", "none"}:
            raise ValueError("Unsupported Jacobian declaration.")
        if "analytic_jacobian" in self.capabilities and self.jacobian != "analytic":
            raise ValueError("analytic_jacobian requires an analytic Jacobian declaration.")
        if "numeric_jacobian" in self.capabilities and self.jacobian != "numeric":
            raise ValueError("numeric_jacobian requires a numeric Jacobian declaration.")
        if self.state_equation not in {"none", "ode", "dae", "discrete"}:
            raise ValueError("Unsupported state-equation form.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": list(self.capabilities), "residual_form": self.residual_form,
            "jacobian": self.jacobian, "state_equation": self.state_equation,
        }


@dataclass(frozen=True, slots=True)
class BehavioralFlags:
    """Physical declarations; active and non-reciprocal devices are valid."""

    four_quadrant: bool = False
    ndr_allowed: bool = False
    passive: bool = False
    reciprocal: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "four_quadrant": self.four_quadrant, "ndr_allowed": self.ndr_allowed,
            "passive": self.passive, "reciprocal": self.reciprocal,
        }


@dataclass(frozen=True, slots=True)
class RuntimeProvenance:
    implementation_kind: str
    implementation_id: str
    sha256: str
    trust: str = "untrusted"
    reviewed_by: str = ""
    build_id: str = ""
    contract: str = RUNTIME_PROVENANCE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != RUNTIME_PROVENANCE_CONTRACT:
            raise ValueError("Unsupported runtime-provenance contract.")
        if self.implementation_kind not in {"builtin_reference", "declarative", "native", "wasm", "python", "hdl"}:
            raise ValueError("Unsupported implementation kind.")
        if not self.implementation_id.strip() or _SHA256_RE.fullmatch(self.sha256) is None:
            raise ValueError("Runtime provenance requires an implementation ID and SHA-256 digest.")
        if self.trust not in {"untrusted", "reviewed", "bundled"}:
            raise ValueError("Unsupported runtime trust state.")
        if self.trust == "reviewed" and not self.reviewed_by.strip():
            raise ValueError("Reviewed runtimes require a named reviewer.")

    @property
    def native_execution_trusted(self) -> bool:
        return self.implementation_kind != "native" or self.trust in {"reviewed", "bundled"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract, "implementation_kind": self.implementation_kind,
            "implementation_id": self.implementation_id, "sha256": self.sha256,
            "trust": self.trust, "reviewed_by": self.reviewed_by, "build_id": self.build_id,
            "native_execution_trusted": self.native_execution_trusted,
        }


@dataclass(frozen=True, slots=True)
class DeviceDescriptor:
    device_id: str
    title: str
    electrical_terminals: tuple[ElectricalTerminal, ...]
    power_ports: tuple[PowerPort, ...]
    variables: tuple[DeviceVariable, ...]
    validity: DeviceValidityEnvelope
    solver: SolverInterface
    behavior: BehavioralFlags
    runtime: RuntimeProvenance
    contract: str = DEVICE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != DEVICE_CONTRACT:
            raise ValueError("Unsupported device contract.")
        _valid_id(self.device_id, "Device ID")
        if not self.title.strip() or not self.electrical_terminals:
            raise ValueError("Devices require a title and at least one electrical terminal.")
        _unique_ids(self.electrical_terminals, "Electrical terminal")
        _unique_ids(self.power_ports, "Power-port")
        _unique_ids(self.variables, "Variable")
        all_ports = [port.port_id for port in self.electrical_terminals + self.power_ports]
        if len(all_ports) != len(set(all_ports)):
            raise ValueError("Port IDs must be unique across all physical domains.")
        variable_roles = {variable.role for variable in self.variables}
        if "observable" not in variable_roles:
            raise ValueError("Devices must expose at least one observable.")
        required = {
            "thermal": "thermal_coupling", "rotational": "rotational_coupling",
            "translational": "translational_coupling", "magnetic": "magnetic_coupling",
            "acoustic": "acoustic_coupling",
        }
        capabilities = set(self.solver.capabilities)
        for port in self.power_ports:
            if required[port.domain] not in capabilities:
                raise ValueError(f"{port.domain} ports require {required[port.domain]} capability.")
        if self.behavior.four_quadrant and "four_quadrant_iv" not in capabilities:
            raise ValueError("Four-quadrant behavior requires four_quadrant_iv capability.")
        if self.behavior.ndr_allowed and "negative_differential_resistance" not in capabilities:
            raise ValueError("NDR behavior requires negative_differential_resistance capability.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract, "id": self.device_id, "title": self.title,
            "electrical_terminals": [port.to_dict() for port in self.electrical_terminals],
            "power_ports": [port.to_dict() for port in self.power_ports],
            "variables": [variable.to_dict() for variable in self.variables],
            "validity": self.validity.to_dict(), "solver": self.solver.to_dict(),
            "behavior": self.behavior.to_dict(), "runtime": self.runtime.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DeviceExtensionManifest:
    extension_id: str
    version: str
    api_version: int
    device_ids: tuple[str, ...]
    required_host_capabilities: tuple[str, ...]
    provenance: RuntimeProvenance
    execution_enabled: bool = False
    contract: str = DEVICE_EXTENSION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != DEVICE_EXTENSION_CONTRACT:
            raise ValueError("Unsupported device-extension contract.")
        _valid_id(self.extension_id, "Extension ID")
        if _VERSION_RE.fullmatch(self.version) is None or self.api_version != 1:
            raise ValueError("Extensions require semantic versioning and API version 1.")
        if not self.device_ids or len(self.device_ids) != len(set(self.device_ids)):
            raise ValueError("Extensions require unique device IDs.")
        for device_id in self.device_ids:
            _valid_id(device_id, "Extension device ID")
        unsupported = set(self.required_host_capabilities) - SUPPORTED_CAPABILITIES
        if unsupported:
            raise ValueError(f"Unsupported host capabilities: {', '.join(sorted(unsupported))}.")
        if self.execution_enabled:
            raise ValueError("Extension execution/loading is not implemented; manifests are metadata only.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract, "id": self.extension_id, "version": self.version,
            "api_version": self.api_version, "device_ids": list(self.device_ids),
            "required_host_capabilities": list(self.required_host_capabilities),
            "provenance": self.provenance.to_dict(), "execution_enabled": False,
        }


__all__ = [
    "DEVICE_CONTRACT", "DEVICE_EXTENSION_CONTRACT", "RUNTIME_PROVENANCE_CONTRACT",
    "SUPPORTED_CAPABILITIES", "PORT_DOMAINS", "BehavioralFlags", "DeviceDescriptor",
    "DeviceExtensionManifest", "DeviceValidityEnvelope", "DeviceVariable",
    "ElectricalTerminal", "PowerPort", "RuntimeProvenance", "SolverInterface",
    "ValidityBound",
]
