"""Strict multi-region OpenFOAM CHT case translation boundary.

This is intentionally a case *preparation* contract.  It creates a
digest-bound, inspectable region/material/interface manifest only after a
caller supplies qualified mesh and contact evidence.  It does not make the
existing single-region OpenFOAM route broader and does not establish solver or
workflow qualification.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, Mapping
from .openfoam_pressure_work import pressure_work_policy
from .openfoam_multiregion_flow import outlets, validate_flow_boundaries, boundary_body, fan_temperature


REQUEST_CONTRACT = "spike/openfoam-multiregion-request/v1"
CASE_CONTRACT = "spike/openfoam-multiregion-case/v1"
ADAPTER_CONTRACT = "spike/openfoam-multiregion-adapter/v1"
ADAPTER_VERSION = "0.1.0"
RUNNABLE_CASE_CONTRACT = "spike/openfoam-multiregion-runnable-case/v1"
MAX_REGIONS = 128
MAX_INTERFACES = 2_048
MAX_MATERIALS = 256
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_BOUNDARY_BLOCK = re.compile(r"(?ms)^\s*([A-Za-z][A-Za-z0-9_]*)\s*\{(.*?)^\s*\}")
_VIEW_FACTOR_EVIDENCE_CONTRACT = "spike/qualified-view-factor-input/v1"
_EMISSIVITY_EVIDENCE_CONTRACT = "spike/qualified-emissivity/v1"
_RADIATION_BOUNDARY_EVIDENCE_CONTRACT = "spike/qualified-radiation-boundary/v1"


class MultiRegionOpenFoamError(ValueError):
    """Raised when evidence cannot be safely translated to a multi-region case."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _finite(value: Any, label: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise MultiRegionOpenFoamError(f"{label} must be finite.")
    result = float(value)
    if positive and result <= 0:
        raise MultiRegionOpenFoamError(f"{label} must be positive.")
    if nonnegative and result < 0:
        raise MultiRegionOpenFoamError(f"{label} must be non-negative.")
    return result


def _identifier(value: Any, label: str) -> str:
    result = str(value or "")
    if not _ID.fullmatch(result):
        raise MultiRegionOpenFoamError(f"{label} must use OpenFOAM-safe identifier syntax.")
    return result


def _evidence(value: Any, label: str) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        raise MultiRegionOpenFoamError(f"{label} evidence must be an object.")
    evidence_id = str(value.get("id") or "")
    digest = str(value.get("sha256") or "")
    contract = str(value.get("contract") or "")
    if not evidence_id or not _DIGEST.fullmatch(digest) or not contract or value.get("qualified") is not True:
        raise MultiRegionOpenFoamError(f"{label} requires non-empty ID/contract, a lowercase SHA-256 digest, and qualified=true.")
    return {"id": evidence_id, "sha256": digest, "contract": contract}


def _contract_evidence(value: Any, label: str, contract: str) -> Dict[str, str]:
    """Require evidence with the exact contract admitted by this translator."""
    evidence = _evidence(value, label)
    if evidence["contract"] != contract:
        raise MultiRegionOpenFoamError(f"{label} must use evidence contract {contract}.")
    return evidence


def _cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise MultiRegionOpenFoamError("OpenFOAM multi-region case preparation cancelled")


def _material(raw: Any) -> Dict[str, Any]:
    from .openfoam_materials import normalize_material
    return normalize_material(raw)


def _region(raw: Any, materials: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MultiRegionOpenFoamError("Every region must be an object.")
    region_id = _identifier(raw.get("id"), "region.id")
    kind = str(raw.get("kind") or "")
    if kind not in {"solid", "fluid"}:
        raise MultiRegionOpenFoamError(f"Region {region_id} kind must be solid or fluid.")
    material_id = _identifier(raw.get("material_id"), f"region {region_id} material_id")
    material = materials.get(material_id)
    if material is None or material["phase"] != kind:
        raise MultiRegionOpenFoamError(f"Region {region_id} material must exist and have matching {kind} phase.")
    role = str(raw.get("role") or "")
    allowed_roles = {"board", "package", "heatsink", "enclosure", "potting", "coating"} if kind == "solid" else {"air", "fluid", "vacuum"}
    if role not in allowed_roles:
        raise MultiRegionOpenFoamError(f"Region {region_id} role is not supported for a {kind} region.")
    ownership = raw.get("boundary_ownership", {})
    if not isinstance(ownership, Mapping) or any(not _ID.fullmatch(str(patch)) or not isinstance(owner, str) or not owner for patch, owner in ownership.items()):
        raise MultiRegionOpenFoamError(f"Region {region_id} boundary_ownership must map safe patch names to non-empty owners.")
    return {"id": region_id, "kind": kind, "role": role, "material_id": material_id, "mesh_evidence": _evidence(raw.get("mesh_evidence"), f"region {region_id} mesh"), "boundary_ownership": {str(patch): str(owner) for patch, owner in sorted(ownership.items())}}


def _interface(raw: Any, regions: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MultiRegionOpenFoamError("Every interface must be an object.")
    interface_id = _identifier(raw.get("id"), "interface.id")
    left = _identifier(raw.get("region_a"), f"interface {interface_id} region_a")
    right = _identifier(raw.get("region_b"), f"interface {interface_id} region_b")
    if left == right or left not in regions or right not in regions:
        raise MultiRegionOpenFoamError(f"Interface {interface_id} must join two distinct declared regions.")
    kind = str(raw.get("kind") or "")
    if kind not in {"conjugate", "thermal_contact"}:
        raise MultiRegionOpenFoamError(f"Interface {interface_id} kind must be conjugate or thermal_contact.")
    result: Dict[str, Any] = {
        "id": interface_id, "region_a": left, "region_b": right, "kind": kind,
        "evidence": _evidence(raw.get("evidence"), f"interface {interface_id}"),
        "patch_a": _identifier(raw.get("patch_a", f"{interface_id}_{left}"), f"interface {interface_id} patch_a"),
        "patch_b": _identifier(raw.get("patch_b", f"{interface_id}_{right}"), f"interface {interface_id} patch_b"),
    }
    if kind == "thermal_contact":
        result["thermal_resistance_k_per_w"] = _finite(raw.get("thermal_resistance_k_per_w"), f"interface {interface_id} thermal_resistance_k_per_w", positive=True)
        result["contact_area_mm2"] = _finite(raw.get("contact_area_mm2"), f"interface {interface_id} contact_area_mm2", positive=True)
        if "openfoam_baffle" in raw:
            if not isinstance(raw["openfoam_baffle"], Mapping):
                raise MultiRegionOpenFoamError(f"Interface {interface_id} openfoam_baffle must be an object.")
            result["openfoam_baffle"] = dict(raw["openfoam_baffle"])
    return result


def _radiation_model(
    environment: Mapping[str, Any],
    regions: Mapping[str, Mapping[str, Any]],
    materials: Mapping[str, Mapping[str, Any]],
    *,
    radiation: bool,
    vacuum: bool,
) -> Dict[str, Any]:
    """Validate either enclosure exchange or exterior-to-background radiation.

    ``viewFactor`` is reserved for radiating surfaces that exchange with one
    another and therefore requires an explicit view-factor preprocessing
    contract. ``externalAmbient`` is the solid-wall Stefan-Boltzmann boundary
    used for vacuum heat rejection to a specified background temperature with
    zero convection. Neither model infers emissivity from a material name.
    """
    if not radiation:
        return {}
    raw = environment.get("radiation_model")
    if not isinstance(raw, Mapping) or raw.get("model") not in {"viewFactor", "externalAmbient"}:
        raise MultiRegionOpenFoamError("Radiation requires model=viewFactor or model=externalAmbient.")
    model = str(raw["model"])
    view_factor_evidence: Dict[str, str] = {}
    validated_controls: Dict[str, Any] = {}
    background_temperature_k = None
    if model == "viewFactor":
        view_factor_evidence = _contract_evidence(
            raw.get("view_factor_evidence"), "radiation view-factor", _VIEW_FACTOR_EVIDENCE_CONTRACT,
        )
        controls = raw.get("view_factor_controls")
        if not isinstance(controls, Mapping):
            raise MultiRegionOpenFoamError("View-factor radiation requires explicit view_factor_controls.")
        validated_controls = {
            "GaussQuadTol": _finite(controls.get("GaussQuadTol"), "radiation GaussQuadTol", positive=True),
            "distTol": _finite(controls.get("distTol"), "radiation distTol", positive=True),
            "alpha": _finite(controls.get("alpha"), "radiation alpha", positive=True),
            "intTol": _finite(controls.get("intTol"), "radiation intTol", positive=True),
            "useDirectSolver": bool(controls.get("useDirectSolver", False)),
        }
    else:
        background_temperature_k = _finite(
            raw.get("background_temperature_k"), "external radiation background_temperature_k", positive=True,
        )
    raw_boundaries = raw.get("boundaries")
    if not isinstance(raw_boundaries, list) or not raw_boundaries or len(raw_boundaries) > 8_192:
        raise MultiRegionOpenFoamError("Radiation requires 1..8192 explicit boundary records.")
    boundaries = []
    seen = set()
    for item in raw_boundaries:
        if not isinstance(item, Mapping):
            raise MultiRegionOpenFoamError("Every radiation boundary must be an object.")
        region_id = _identifier(item.get("region_id"), "radiation boundary region_id")
        patch = _identifier(item.get("patch"), "radiation boundary patch")
        region = regions.get(region_id)
        if region is None:
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} references an undeclared region.")
        if vacuum and region["kind"] != "solid":
            raise MultiRegionOpenFoamError("Vacuum radiation boundaries must be declared on solid regions, never a pseudo-fluid vacuum region.")
        material_id = _identifier(item.get("material_id"), f"radiation boundary {region_id}:{patch} material_id")
        if material_id != region["material_id"]:
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} material_id must match its region material.")
        material = materials[material_id]
        emissivity = _finite(item.get("emissivity"), f"radiation boundary {region_id}:{patch} emissivity", positive=True)
        if emissivity > 1:
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} emissivity must not exceed one.")
        if "emissivity" not in material or not math.isclose(emissivity, float(material["emissivity"]), rel_tol=0.0, abs_tol=1e-12):
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} emissivity must exactly match qualified material emissivity.")
        key = (region_id, patch)
        if key in seen:
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} is declared more than once.")
        seen.add(key)
        external_flux = _finite(item.get("external_radiative_flux_w_m2"), f"radiation boundary {region_id}:{patch} external_radiative_flux_w_m2", nonnegative=True)
        if model == "externalAmbient" and external_flux != 0:
            raise MultiRegionOpenFoamError("externalAmbient radiation does not admit a separate incident-flux term; use zero or a qualified view-factor model.")
        boundaries.append({
            "region_id": region_id, "patch": patch, "material_id": material_id, "emissivity": emissivity,
            "external_radiative_flux_w_m2": external_flux,
            "emissivity_evidence": _contract_evidence(item.get("emissivity_evidence"), f"radiation boundary {region_id}:{patch} emissivity", _EMISSIVITY_EVIDENCE_CONTRACT),
            "boundary_evidence": _contract_evidence(item.get("boundary_evidence"), f"radiation boundary {region_id}:{patch}", _RADIATION_BOUNDARY_EVIDENCE_CONTRACT),
        })
    result: Dict[str, Any] = {
        "model": model,
        "boundaries": sorted(boundaries, key=lambda value: (value["region_id"], value["patch"])),
    }
    if model == "viewFactor":
        result.update({"view_factor_evidence": view_factor_evidence, "view_factor_controls": validated_controls})
    else:
        result["background_temperature_k"] = background_temperature_k
    return result


def compile_multiregion_case(request: Mapping[str, Any], *, cancel_check: Callable[[], bool] | None = None) -> Dict[str, Any]:
    """Compile evidence-backed OpenFOAM multi-region metadata without running it."""
    if not isinstance(request, Mapping) or request.get("contract") != REQUEST_CONTRACT:
        raise MultiRegionOpenFoamError(f"Expected {REQUEST_CONTRACT}.")
    _cancel(cancel_check)
    root_mesh = _evidence(request.get("mesh_evidence"), "assembly mesh")
    raw_materials = request.get("materials")
    raw_regions = request.get("regions")
    raw_interfaces = request.get("interfaces")
    if not isinstance(raw_materials, list) or not 1 <= len(raw_materials) <= MAX_MATERIALS:
        raise MultiRegionOpenFoamError(f"materials must contain 1..{MAX_MATERIALS} records.")
    if not isinstance(raw_regions, list) or not 1 <= len(raw_regions) <= MAX_REGIONS:
        raise MultiRegionOpenFoamError(f"regions must contain 1..{MAX_REGIONS} records.")
    if not isinstance(raw_interfaces, list) or len(raw_interfaces) > MAX_INTERFACES:
        raise MultiRegionOpenFoamError(f"interfaces must contain 0..{MAX_INTERFACES} records.")
    materials = [_material(item) for item in raw_materials]
    material_ids = [item["id"] for item in materials]
    if len(material_ids) != len(set(material_ids)):
        raise MultiRegionOpenFoamError("Material IDs must be unique.")
    material_map = {item["id"]: item for item in materials}
    _cancel(cancel_check)
    regions = [_region(item, material_map) for item in raw_regions]
    region_ids = [item["id"] for item in regions]
    if len(region_ids) != len(set(region_ids)):
        raise MultiRegionOpenFoamError("Region IDs must be unique.")
    region_map = {item["id"]: item for item in regions}
    interfaces = [_interface(item, region_map) for item in raw_interfaces]
    interface_ids = [item["id"] for item in interfaces]
    if len(interface_ids) != len(set(interface_ids)):
        raise MultiRegionOpenFoamError("Interface IDs must be unique.")
    pairs = [tuple(sorted((item["region_a"], item["region_b"]))) for item in interfaces]
    if len(pairs) != len(set(pairs)):
        raise MultiRegionOpenFoamError("Only one explicit interface may join each pair of regions.")
    raw_sources = request.get("heat_sources", [])
    if not isinstance(raw_sources, list) or len(raw_sources) > 10_000:
        raise MultiRegionOpenFoamError("heat_sources must contain at most 10000 records.")
    heat_sources = []
    for source in raw_sources:
        if not isinstance(source, Mapping):
            raise MultiRegionOpenFoamError("Every heat source must be an object.")
        source_id = _identifier(source.get("id"), "heat_source.id")
        region_id = _identifier(source.get("solid_region_id"), f"heat source {source_id} solid_region_id")
        if region_id not in region_map or region_map[region_id]["kind"] != "solid":
            raise MultiRegionOpenFoamError(f"Heat source {source_id} must target a declared solid region.")
        option = source.get("fv_option", {})
        if option and (not isinstance(option, Mapping) or not _ID.fullmatch(str(option.get("cell_zone") or ""))):
            raise MultiRegionOpenFoamError(f"Heat source {source_id} fv_option requires an OpenFOAM-safe cell_zone.")
        heat_sources.append({"id": source_id, "solid_region_id": region_id, "power_w": _finite(source.get("power_w"), f"heat source {source_id} power_w", nonnegative=True), "evidence": _evidence(source.get("evidence"), f"heat source {source_id}"), "fv_option": ({"cell_zone": str(option["cell_zone"]), "volumetric_power_w_m3": _finite(option.get("volumetric_power_w_m3"), f"heat source {source_id} fv_option volumetric_power_w_m3", nonnegative=True)} if option else {})})
    source_ids = [item["id"] for item in heat_sources]
    if len(source_ids) != len(set(source_ids)):
        raise MultiRegionOpenFoamError("Heat-source IDs must be unique.")
    _cancel(cancel_check)
    environment = request.get("environment", {})
    if not isinstance(environment, Mapping):
        raise MultiRegionOpenFoamError("environment must be an object.")
    enclosure = str(environment.get("enclosure", "open"))
    if enclosure not in {"open", "sealed", "vented_cabinet"}:
        raise MultiRegionOpenFoamError("environment.enclosure is unsupported.")
    radiation = bool(environment.get("radiation", False))
    vacuum = bool(environment.get("vacuum", False))
    raw_gravity = environment.get("gravity_m_s2", [0.0, 0.0, 0.0])
    if not isinstance(raw_gravity, list) or len(raw_gravity) != 3:
        raise MultiRegionOpenFoamError("environment.gravity_m_s2 must contain three finite components.")
    gravity = [_finite(value, f"environment.gravity_m_s2[{index}]") for index, value in enumerate(raw_gravity)]
    if any(abs(value) > 100 for value in gravity):
        raise MultiRegionOpenFoamError("environment.gravity_m_s2 components must not exceed 100 m/s2.")
    if enclosure != "open" and not any(item["role"] == "enclosure" for item in regions):
        raise MultiRegionOpenFoamError("A sealed or vented enclosure requires an explicit enclosure solid region.")
    if vacuum and not radiation:
        raise MultiRegionOpenFoamError("Vacuum multi-region thermal cases require explicit radiation metadata.")
    solid_regions = [item for item in regions if item["kind"] == "solid"]
    fluid_regions = [item for item in regions if item["kind"] == "fluid"]
    if vacuum:
        if str(environment.get("medium", "")) != "vacuum":
            raise MultiRegionOpenFoamError("Vacuum cases require environment.medium=vacuum.")
        if not solid_regions or fluid_regions:
            raise MultiRegionOpenFoamError("Vacuum cases require one or more solid regions and cannot contain pseudo-fluid regions.")
    elif not solid_regions or not fluid_regions:
        raise MultiRegionOpenFoamError("A conjugate thermal case requires at least one solid and one fluid region.")
    if str(environment.get("medium", "air")) == "potting" and not any(item["role"] == "potting" for item in regions):
        raise MultiRegionOpenFoamError("Potting medium requires an explicit potting solid region.")
    radiation_model = _radiation_model(
        environment, region_map, material_map, radiation=radiation, vacuum=vacuum,
    )
    raw_fans = request.get("fans", [])
    if not isinstance(raw_fans, list) or len(raw_fans) > 64:
        raise MultiRegionOpenFoamError("fans must contain at most 64 records.")
    fans = []
    for index, fan in enumerate(raw_fans):
        if not isinstance(fan, Mapping):
            raise MultiRegionOpenFoamError("Every fan must be an object.")
        fan_id = _identifier(fan.get("id"), "fan.id")
        region_id = _identifier(fan.get("fluid_region_id"), f"fan {fan_id} fluid_region_id")
        if region_id not in region_map or region_map[region_id]["kind"] != "fluid":
            raise MultiRegionOpenFoamError(f"Fan {fan_id} must target a declared fluid region.")
        if vacuum:
            raise MultiRegionOpenFoamError("Vacuum cases cannot contain fans.")
        patch = str(fan.get("boundary_patch") or "")
        if patch and not _ID.fullmatch(patch):
            raise MultiRegionOpenFoamError(f"Fan {fan_id} boundary_patch must use OpenFOAM-safe identifier syntax.")
        fans.append({"id": fan_id, "fluid_region_id": region_id, "flow_rate_m3_s": _finite(fan.get("flow_rate_m3_s"), f"fan {fan_id} flow_rate_m3_s", positive=True), "boundary_evidence": _evidence(fan.get("boundary_evidence"), f"fan {fan_id} boundary"), "boundary_patch": patch})
    for fan, raw in zip(fans, raw_fans):
        fan["inlet_temperature_k"] = fan_temperature(raw, environment)
    pressure_outlets = outlets(environment, region_map)
    raw_heatsinks = request.get("heatsinks", [])
    if not isinstance(raw_heatsinks, list) or len(raw_heatsinks) > 256:
        raise MultiRegionOpenFoamError("heatsinks must contain at most 256 records.")
    heatsinks = []
    for sink in raw_heatsinks:
        if not isinstance(sink, Mapping):
            raise MultiRegionOpenFoamError("Every heatsink must be an object.")
        sink_id = _identifier(sink.get("id"), "heatsink.id")
        region_id = _identifier(sink.get("region_id"), f"heatsink {sink_id} region_id")
        if region_id not in region_map or region_map[region_id]["role"] != "heatsink":
            raise MultiRegionOpenFoamError(f"Heatsink {sink_id} must reference a declared heatsink solid region.")
        heatsinks.append({"id": sink_id, "region_id": region_id, "mount_interface_id": _identifier(sink.get("mount_interface_id"), f"heatsink {sink_id} mount_interface_id")})
    if any(item["role"] == "heatsink" for item in regions) and not heatsinks:
        raise MultiRegionOpenFoamError("Every heatsink region requires an explicit heatsink mount record.")
    interface_map = {item["id"]: item for item in interfaces}
    if any(item["mount_interface_id"] not in interface_map for item in heatsinks):
        raise MultiRegionOpenFoamError("Every heatsink mount must reference a declared interface.")
    raw_numerics = request.get("numerics", {})
    if not isinstance(raw_numerics, Mapping):
        raise MultiRegionOpenFoamError("numerics must be an object.")
    end_time_s = _finite(raw_numerics.get("end_time_s", 100.0), "numerics.end_time_s", positive=True)
    delta_t_s = _finite(raw_numerics.get("delta_t_s", 1.0), "numerics.delta_t_s", positive=True)
    if delta_t_s > end_time_s:
        raise MultiRegionOpenFoamError("numerics.delta_t_s must not exceed end_time_s.")
    write_interval_steps = raw_numerics.get("write_interval_steps", max(1, int(round(end_time_s / delta_t_s / 10))))
    if not isinstance(write_interval_steps, int) or isinstance(write_interval_steps, bool) or not 1 <= write_interval_steps <= 1_000_000:
        raise MultiRegionOpenFoamError("numerics.write_interval_steps must be an integer from 1 to 1000000.")
    if end_time_s / delta_t_s > 10_000_000:
        raise MultiRegionOpenFoamError("numerics requests more than 10000000 time steps.")
    validation_interval_steps = raw_numerics.get("validation_interval_steps", write_interval_steps)
    if not isinstance(validation_interval_steps, int) or isinstance(validation_interval_steps, bool) or not 1 <= validation_interval_steps <= 1_000_000:
        raise MultiRegionOpenFoamError("numerics.validation_interval_steps must be an integer from 1 to 1000000.")
    outer_correctors = raw_numerics.get("outer_correctors", 1)
    if not isinstance(outer_correctors, int) or isinstance(outer_correctors, bool) or not 1 <= outer_correctors <= 50:
        raise MultiRegionOpenFoamError("numerics.outer_correctors must be an integer from 1 to 50.")
    numerics = {"transient": True, "end_time_s": end_time_s, "delta_t_s": delta_t_s, "write_interval_steps": write_interval_steps, "validation_interval_steps": validation_interval_steps, "outer_correctors": outer_correctors}
    from .openfoam_turbulence import admit_turbulence
    turbulence_model = admit_turbulence(environment, gravity, materials, fans, fluid_regions)
    _cancel(cancel_check)
    return {
        "contract": CASE_CONTRACT, "adapter_contract": ADAPTER_CONTRACT, "adapter_version": ADAPTER_VERSION,
        "status": "prepared_not_runnable", "solver": {"command": "chtMultiRegionFoam", "runtime_probe_required": True, "qualification": "not_established"},
        "assembly_mesh_evidence": root_mesh, "materials": sorted(materials, key=lambda item: item["id"]), "regions": sorted(regions, key=lambda item: item["id"]),
        "interfaces": sorted(interfaces, key=lambda item: item["id"]), "environment": {"enclosure": enclosure, "radiation": radiation, "vacuum": vacuum, "medium": str(environment.get("medium", "air")), "ambient_temperature_k": _finite(environment.get("ambient_temperature_k", 298.15), "environment ambient_temperature_k", positive=True), "gravity_m_s2": gravity, "radiation_model": radiation_model, "pressure_outlets": pressure_outlets, **({"turbulence_model": turbulence_model} if turbulence_model is not None else {}), **pressure_work_policy(environment,materials,gravity)},
        "heat_sources": sorted(heat_sources, key=lambda item: item["id"]), "fans": sorted(fans, key=lambda item: item["id"]), "heatsinks": sorted(heatsinks, key=lambda item: item["id"]),
        "numerics": numerics,
        "requested_physics": {"solid_conduction": True, "fluid_flow": bool(fluid_regions) and (bool(fans) or any(abs(value) > 0 for value in gravity) or any(item.get("density_model") for item in materials)), "conjugate_heat_transfer": bool(fluid_regions), "radiation": radiation, "vacuum": vacuum, "potting": any(item["role"] == "potting" for item in regions), "coatings": any(item["role"] == "coating" for item in regions)},
        "qualification": {"solver_ready": False, "field_result_produced": False, "production_qualified": False, "reason": "Strict region translation is not numerical validation, a runnable OpenFOAM dictionary set, or a thermal result."},
    }


def _write(root: Path, relative: str, content: str) -> None:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise MultiRegionOpenFoamError("Generated case file escaped its case directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def _file_digests(root: Path) -> Dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink() and path.name != "spike_multiregion_case.json"}


def _foam_file(class_name: str, object_name: str, body: str, *, location: str) -> str:
    return f"FoamFile\n{{\n    version 2.0;\n    format ascii;\n    class {class_name};\n    location \"{location}\";\n    object {object_name};\n}}\n\n{body}"


def poly_mesh_digest(poly_mesh: str | Path) -> str:
    """Digest a materialized polyMesh tree by relative file name and bytes."""
    root = Path(poly_mesh).resolve()
    required = ("points", "faces", "owner", "neighbour", "boundary")
    if not root.is_dir() or root.is_symlink() or any(not (root / name).is_file() or (root / name).is_symlink() for name in required):
        raise MultiRegionOpenFoamError("A materialized polyMesh requires regular points, faces, owner, neighbour, and boundary files.")
    files: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise MultiRegionOpenFoamError("A materialized polyMesh may not contain symbolic links.")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _digest(files)


def _boundary_patches(poly_mesh: Path) -> Dict[str, set[str]]:
    try:
        text = (poly_mesh / "boundary").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MultiRegionOpenFoamError("The materialized polyMesh boundary file is unreadable.") from exc
    # Parse only the boundary-list body.  The FoamFile header can itself use a
    # brace pair on one line and must never be interpreted as a patch record.
    list_start = re.search(r"(?m)^\s*\(\s*$", text)
    records = _BOUNDARY_BLOCK.findall(text[list_start.end():] if list_start else "")
    if not records:
        raise MultiRegionOpenFoamError("The materialized polyMesh boundary file contains no parseable patch records.")
    records_by_name: Dict[str, set[str]] = {}
    for name, body in records:
        if not _ID.fullmatch(name) or name in records_by_name or not re.search(r"\bnFaces\s+\d+\s*;", body) or not re.search(r"\bstartFace\s+\d+\s*;", body):
            raise MultiRegionOpenFoamError("Materialized polyMesh boundary patches must have unique safe names, nFaces, and startFace.")
        match = re.search(r"\binGroups\s+\d+\s*\(([^)]*)\)\s*;", body)
        groups = set(match.group(1).split()) if match else set()
        if any(not _ID.fullmatch(group) for group in groups):
            raise MultiRegionOpenFoamError("Materialized polyMesh boundary groups must use safe identifiers.")
        records_by_name[name] = groups
    return records_by_name


def _cell_zones(poly_mesh: Path) -> set[str]:
    path = poly_mesh / "cellZones"
    if not path.exists():
        return set()
    if not path.is_file() or path.is_symlink():
        raise MultiRegionOpenFoamError("Materialized polyMesh cellZones must be a regular file.")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MultiRegionOpenFoamError("The materialized polyMesh cellZones file is unreadable.") from exc
    list_start = re.search(r"(?m)^\s*\(\s*$", text)
    records = _BOUNDARY_BLOCK.findall(text[list_start.end():] if list_start else "")
    names = set()
    for name, body in records:
        if not _ID.fullmatch(name) or name in names or not re.search(r"\btype\s+cellZone\s*;", body) or "cellLabels" not in body:
            raise MultiRegionOpenFoamError("Materialized polyMesh cell zones must have unique safe names and explicit cellLabels.")
        names.add(name)
    if not names:
        raise MultiRegionOpenFoamError("The materialized polyMesh cellZones file contains no parseable zones.")
    return names


def _materialized_meshes(case: Mapping[str, Any], mesh_root: str | Path) -> Dict[str, Dict[str, Any]]:
    root = Path(mesh_root).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise MultiRegionOpenFoamError("materialized_mesh_root must be a non-symbolic-link directory.")
    meshes: Dict[str, Dict[str, Any]] = {}
    for region in case["regions"]:
        region_id = str(region["id"])
        poly_mesh = (root / region_id / "polyMesh").resolve()
        if not poly_mesh.is_relative_to(root):
            raise MultiRegionOpenFoamError("A materialized polyMesh escaped its declared root.")
        digest = poly_mesh_digest(poly_mesh)
        if digest != region["mesh_evidence"]["sha256"]:
            raise MultiRegionOpenFoamError(f"Materialized polyMesh digest does not match qualified evidence for region {region_id}.")
        patch_groups = _boundary_patches(poly_mesh)
        patches = set(patch_groups)
        ownership = region.get("boundary_ownership", {})
        if set(ownership) != patches:
            raise MultiRegionOpenFoamError(f"Declared boundary ownership does not exactly match materialized polyMesh patches for region {region_id}.")
        meshes[region_id] = {"poly_mesh": poly_mesh, "digest": digest, "patches": patches, "patch_groups": patch_groups, "cell_zones": _cell_zones(poly_mesh), "ownership": dict(ownership)}
    interface_ids = {str(item["id"]) for item in case["interfaces"]}
    for interface in case["interfaces"]:
        left, right, interface_id = interface["region_a"], interface["region_b"], interface["id"]
        for region_id, patch, expected_owner in ((left, interface["patch_a"], f"interface:{interface_id}"), (right, interface["patch_b"], f"interface:{interface_id}")):
            if meshes[region_id]["ownership"].get(patch) != expected_owner:
                raise MultiRegionOpenFoamError(f"Interface {interface_id} must own patch {patch} exactly once in region {region_id}.")
    for fan in case["fans"]:
        patch = str(fan.get("boundary_patch") or "")
        if not patch or meshes[fan["fluid_region_id"]]["ownership"].get(patch) != f"fan:{fan['id']}":
            raise MultiRegionOpenFoamError(f"Fan {fan['id']} requires an exactly owned boundary_patch in its fluid region.")
    for source in case["heat_sources"]:
        option = source.get("fv_option") or {}
        zone = str(option.get("cell_zone") or "")
        if zone and zone not in meshes[source["solid_region_id"]]["cell_zones"]:
            raise MultiRegionOpenFoamError(f"Heat source {source['id']} requires materialized cell zone {zone} in region {source['solid_region_id']}.")
    for boundary in case["environment"].get("radiation_model", {}).get("boundaries", []):
        region_id, patch = boundary["region_id"], boundary["patch"]
        mesh = meshes[region_id]
        if patch not in mesh["patches"] or not mesh["ownership"].get(patch, "").startswith("external:"):
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} must be an exactly owned external materialized patch.")
        if boundary["boundary_evidence"]["sha256"] != mesh["digest"]:
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} evidence must bind the exact materialized polyMesh digest.")
        if case["environment"].get("radiation_model", {}).get("model") == "viewFactor" and "viewFactorWall" not in mesh["patch_groups"].get(patch, set()):
            raise MultiRegionOpenFoamError(f"Radiation boundary {region_id}:{patch} must belong to the materialized viewFactorWall patch group.")
    for region_id, mesh in meshes.items():
        for owner in mesh["ownership"].values():
            if owner.startswith("interface:") and owner.split(":", 1)[1] not in interface_ids:
                raise MultiRegionOpenFoamError(f"Region {region_id} declares an unknown interface boundary owner.")
            if not (owner.startswith("interface:") or owner.startswith("fan:") or owner.startswith("external:")):
                raise MultiRegionOpenFoamError(f"Region {region_id} boundary ownership must be interface:, fan:, or external:.")
    validate_flow_boundaries(case, meshes)
    return meshes


def _boundary_field(case: Mapping[str, Any], region: Mapping[str, Any], meshes: Mapping[str, Mapping[str, Any]], field: str) -> str:
    ambient = float(case["environment"]["ambient_temperature_k"])
    interface_by_region_patch: Dict[str, Mapping[str, Any]] = {}
    for interface in case["interfaces"]:
        interface_by_region_patch[f"{interface['region_a']}:{interface['patch_a']}"] = interface
        interface_by_region_patch[f"{interface['region_b']}:{interface['patch_b']}"] = interface
    radiation_by_region_patch = {
        f"{item['region_id']}:{item['patch']}": item
        for item in case["environment"].get("radiation_model", {}).get("boundaries", [])
    }
    blocks = []
    for patch in sorted(meshes[region["id"]]["patches"]):
        owner = meshes[region["id"]]["ownership"][patch]
        interface = interface_by_region_patch.get(f"{region['id']}:{patch}")
        radiation_boundary = radiation_by_region_patch.get(f"{region['id']}:{patch}")
        radiation_model = case["environment"].get("radiation_model", {})
        flow_body = boundary_body(case, region, patch, owner, field)
        if flow_body is not None:
            blocks.append(f"    {patch}\n    {{\n        {flow_body}\n    }}")
        elif field == "T" and radiation_boundary is not None and radiation_model.get("model") == "externalAmbient":
            background = radiation_model["background_temperature_k"]
            blocks.append(
                f"    {patch}\n    {{\n"
                "        type externalWallHeatFluxTemperature;\n"
                "        mode coefficient;\n"
                f"        Ta constant {background};\n"
                "        h constant 0;\n"
                f"        emissivity {radiation_boundary['emissivity']};\n"
                "        kappaMethod solidThermo;\n"
                f"        value uniform {ambient};\n"
                "    }"
            )
        elif field == "T" and radiation_boundary is not None:
            # v2606's grey-diffuse view-factor field requires the explicit qro
            # entry; the separately generated boundaryRadiationProperties file
            # supplies the evidence-bound emissivity.
            blocks.append(f"    {patch}\n    {{\n        type greyDiffusiveRadiationViewFactor;\n        qro uniform {radiation_boundary['external_radiative_flux_w_m2']};\n        value uniform {ambient};\n    }}")
        elif field == "T" and interface is not None:
            thermo = "solidThermo" if region["kind"] == "solid" else "fluidThermo"
            extra = ""
            if interface["kind"] == "thermal_contact":
                # The physically dimensioned baffle entry is carried only when
                # the caller supplied it; otherwise runnable generation blocks.
                baffle = interface["openfoam_baffle"]
                extra = f"        thicknessLayers ({baffle['thickness_m']});\n        kappaLayers ({baffle['conductivity_w_mk']});\n"
            blocks.append(f"    {patch}\n    {{\n        type compressible::turbulentTemperatureRadCoupledMixed;\n        Tnbr T;\n        qr none;\n        qrNbr none;\n        kappaMethod {thermo};\n{extra}        value uniform {ambient};\n    }}")
        elif field == "T" and owner == "external:fixed_temperature":
            blocks.append(f"    {patch}\n    {{\n        type fixedValue;\n        value uniform {ambient};\n    }}")
        elif field == "T":
            blocks.append(f"    {patch}\n    {{\n        type zeroGradient;\n    }}")
        elif region["kind"] == "fluid" and field == "U" and owner.startswith("fan:"):
            fan = next(item for item in case["fans"] if owner == f"fan:{item['id']}")
            blocks.append(f"    {patch}\n    {{\n        type flowRateInletVelocity;\n        volumetricFlowRate constant {fan['flow_rate_m3_s']};\n        value uniform (0 0 0);\n    }}")
        elif region["kind"] == "fluid" and field == "U":
            blocks.append(f"    {patch}\n    {{\n        type noSlip;\n    }}")
        elif region["kind"] == "fluid" and field == "p_rgh":
            pressure = next((item["static_pressure_pa"] for item in case["environment"].get("pressure_outlets", []) if item["fluid_region_id"] == region["id"]), 101325)
            blocks.append(f"    {patch}\n    {{\n        type fixedFluxPressure;\n        value uniform {pressure:.17g};\n    }}")
    return "boundaryField\n{\n" + "\n".join(blocks) + "\n}\n"


def _thermophysical_properties(material: Mapping[str, Any]) -> str:
    density=f"rho {material['density_kg_m3']};"
    if material["phase"] == "solid":
        thermo_type = "type heSolidThermo;\n    mixture pureMixture;\n    transport constIso;\n    thermo hConst;\n    equationOfState rhoConst;\n    specie specie;\n    energy sensibleEnthalpy;"
    else:
        thermo_type = "type heRhoThermo;\n    mixture pureMixture;\n    transport const;\n    thermo hConst;\n    equationOfState rhoConst;\n    specie specie;\n    energy sensibleEnthalpy;"
        if material.get("density_model"):
            from .openfoam_buoyancy import validate_density_model
            model=validate_density_model(material["density_model"],material["density_kg_m3"])
            thermo_type=thermo_type.replace("equationOfState rhoConst;","equationOfState Boussinesq;")
            density=f"rho0 {model['rho0_kg_m3']:.17g};\n        T0 {model['T0_k']:.17g};\n        beta {model['beta_per_k']:.17g};"
    if material["phase"] == "fluid":
        prandtl = material["specific_heat_j_kgk"] * material["dynamic_viscosity_pa_s"] / material["conductivity_w_mk"]
        transport = f"mu {material['dynamic_viscosity_pa_s']};\n        Pr {prandtl:.17g};"
    else:
        transport = f"kappa {material['conductivity_w_mk']};"
    return f"thermoType\n{{\n    {thermo_type}\n}}\n\nmixture\n{{\n    specie\n    {{\n        molWeight 1;\n    }}\n    thermodynamics\n    {{\n        Cp {material['specific_heat_j_kgk']};\n        Hf 0;\n    }}\n    transport\n    {{\n        {transport}\n    }}\n    equationOfState\n    {{\n        {density}\n    }}\n}}\n"


def _fv_options(case: Mapping[str, Any], region_id: str) -> str:
    source_blocks = []
    for source in case["heat_sources"]:
        if source["solid_region_id"] != region_id:
            continue
        option = source["fv_option"]
        if not option:
            raise MultiRegionOpenFoamError(f"Heat source {source['id']} requires qualified fv_option cell-zone and volumetric power metadata for runnable case generation.")
        source_blocks.append(f"{source['id']}\n{{\n    type scalarSemiImplicitSource;\n    active yes;\n    selectionMode cellZone;\n    cellZone {option['cell_zone']};\n    volumeMode specific;\n    injectionRateSuSp\n    {{\n        h ({option['volumetric_power_w_m3']} 0);\n    }}\n}}")
    return "\n\n".join(source_blocks) + ("\n" if source_blocks else "")


def _radiation_properties(case: Mapping[str, Any], region_id: str) -> str:
    model = case["environment"].get("radiation_model", {})
    boundaries = [item for item in model.get("boundaries", []) if item["region_id"] == region_id]
    if not boundaries or model.get("model") != "viewFactor":
        return "radiationModel none;\n"
    controls = model["view_factor_controls"]
    return (
        "radiationModel viewFactor;\n"
        "viewFactorCoeffs\n{\n"
        "    smoothing false;\n"
        "    constantEmissivity true;\n"
        "    nBands 1;\n"
        f"    useDirectSolver {'true' if controls['useDirectSolver'] else 'false'};\n"
        "}\n"
    )


def _boundary_radiation_properties(case: Mapping[str, Any], region_id: str) -> str:
    if case["environment"].get("radiation_model", {}).get("model") != "viewFactor":
        return ""
    boundaries = [item for item in case["environment"].get("radiation_model", {}).get("boundaries", []) if item["region_id"] == region_id]
    blocks = []
    for item in boundaries:
        emissivity = item["emissivity"]
        blocks.append(
            f"{item['patch']}\n{{\n"
            "    type opaqueDiffusive;\n"
            "    wallAbsorptionEmissionModel\n    {\n"
            "        type lookup;\n"
            f"        absorptivity {emissivity};\n"
            f"        emissivity {emissivity};\n"
            "        transmissivity 0;\n"
            "    }\n"
            "}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _view_factors_dict(case: Mapping[str, Any], region_id: str) -> str:
    model = case["environment"].get("radiation_model", {})
    if model.get("model") != "viewFactor":
        return ""
    patches = [item["patch"] for item in model.get("boundaries", []) if item["region_id"] == region_id]
    if not patches:
        return ""
    controls = model["view_factor_controls"]
    return (
        "// Evidence-bound input for OpenFOAM v2606 viewFactorsGen.\n"
        f"// viewFactorEvidence {model['view_factor_evidence']['sha256']}\n"
        "writeFacesAgglomeration true;\n"
        "writeViewFactorMatrix false;\n"
        "debug 0;\n"
        "dumpRays false;\n"
        f"GaussQuadTol {controls['GaussQuadTol']};\n"
        f"distTol {controls['distTol']};\n"
        f"alpha {controls['alpha']};\n"
        f"intTol {controls['intTol']};\n"
        "patchAgglomeration\n{\n"
        + "\n".join(
            f"    {patch}\n    {{\n        nFacesInCoarsestLevel 30;\n        featureAngle 10;\n    }}"
            for patch in sorted(patches)
        )
        + "\n}\n"
    )


def _fv_schemes(region_kind: str) -> str:
    """Return v2606 schemes appropriate to the region energy equation.

    OpenFOAM v2606 corrected the solid heat-flux formulation and documents
    harmonic interpolation for isotropic ``alpha``/``kappa`` diffusion.  A
    generic linear default can create a conductivity-weighted interface-flux
    error, especially across PCB material zones, so solids name both energy
    operators explicitly.
    """
    common = (
        "ddtSchemes { default Euler; }\n"
        "gradSchemes { default Gauss linear; }\n"
    )
    if region_kind == "solid":
        return common + (
            "divSchemes { default none; }\n"
            "laplacianSchemes\n"
            "{\n"
            "    default none;\n"
            "    laplacian(alpha,h) Gauss harmonic limited corrected 0.5;\n"
            "    laplacian(kappa,h) Gauss harmonic limited corrected 0.5;\n"
            "}\n"
            "interpolationSchemes { default linear; }\n"
            "snGradSchemes { default corrected; }\n"
            "fluxRequired { default no; }\n"
        )
    return common + (
        "divSchemes { default none; div(phi,U) Gauss upwind; div(phi,h) Gauss upwind; "
        "div(phi,K) Gauss upwind; div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear; }\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n"
        "fluxRequired { default no; p_rgh; }\n"
    )


def _runnable_dictionaries(case: Mapping[str, Any], meshes: Mapping[str, Mapping[str, Any]], root: Path) -> None:
    # Deferred import prevents a module cycle while keeping this private seam
    # patchable for callers that already instrumented case preparation.
    from .openfoam_multiregion_render import write_runnable_dictionaries

    write_runnable_dictionaries(case, meshes, root)


def prepare_runnable_multiregion_case(request: Mapping[str, Any], output_dir: str | Path, materialized_mesh_root: str | Path, *, cancel_check: Callable[[], bool] | None = None) -> Dict[str, Any]:
    """Generate a v2606 CHT dictionary tree from qualified materialized meshes.

    The output is a runnable *case shape* only; this method neither probes nor
    executes OpenFOAM and retains all qualification flags as false.
    """
    case = compile_multiregion_case(request, cancel_check=cancel_check)
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        return {"status": "blocked", "message": "Runnable multi-region case directory must be empty to prevent stale input reuse."}
    try:
        meshes = _materialized_meshes(case, materialized_mesh_root)
    except MultiRegionOpenFoamError as exc:
        return {"status": "blocked", "message": str(exc), "qualification": case["qualification"]}
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        return {"status": "blocked", "message": "Runnable multi-region case directory must not be a symbolic link."}
    try:
        _cancel(cancel_check)
        _runnable_dictionaries(case, meshes, root)
        _cancel(cancel_check)
    except MultiRegionOpenFoamError as exc:
        # No manifest is emitted, so an incomplete case cannot be mistaken for an admitted execution input.
        return {"status": "blocked", "message": str(exc), "qualification": case["qualification"]}
    request_digest = _digest(request)
    prepared_manifest = {**case, "status": "prepared_runnable_case", "request_digest": request_digest, "materialized_meshes": {region_id: {"sha256": value["digest"], "patches": sorted(value["patches"]), "ownership": value["ownership"]} for region_id, value in sorted(meshes.items())}, "files": _file_digests(root), "qualification": {**case["qualification"], "reason": "A v2606 dictionary tree is prepared from verified meshes; runtime probe, solver execution, convergence, and validation remain separate."}}
    _write(root, "spike_multiregion_case.json", json.dumps(prepared_manifest, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    input_files = _file_digests(root)
    input_files["spike_multiregion_case.json"] = hashlib.sha256((root / "spike_multiregion_case.json").read_bytes()).hexdigest()
    runnable_manifest = {
        "contract": RUNNABLE_CASE_CONTRACT, "status": "runnable", "solver": "chtMultiRegionFoam",
        "job_id": str(request.get("job_id") or ""), "plan_digest": str(request.get("plan_digest") or request_digest),
        "request_digest": request_digest, "regions": [item["id"] for item in case["regions"]],
        "region_kinds": {item["id"]: item["kind"] for item in case["regions"]},
        "region_conductivity_w_mk": {item["id"]: next(material["conductivity_w_mk"] for material in case["materials"] if material["id"] == item["material_id"]) for item in case["regions"]},
        "view_factor_regions": sorted({
            item["region_id"]
            for item in case["environment"].get("radiation_model", {}).get("boundaries", [])
        }) if case["environment"].get("radiation_model", {}).get("model") == "viewFactor" else [],
        "input_files": input_files, "field_export_path": "postProcessing/spike/fields.json",
        "qualification": {"production_qualified": False, "reason": "Runnable case preparation is not numerical or release qualification."},
    }
    runnable_manifest["manifest_digest"] = _digest(runnable_manifest)
    _write(root, "spike_multiregion_runnable_case.json", json.dumps(runnable_manifest, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    return {"status": "prepared_runnable_case", "case_dir": str(root), "manifest": prepared_manifest, "runnable_manifest": runnable_manifest}


def prepare_multiregion_case(request: Mapping[str, Any], output_dir: str | Path, *, cancel_check: Callable[[], bool] | None = None) -> Dict[str, Any]:
    """Write an inspectable, non-runnable multi-region OpenFOAM preparation tree."""
    case = compile_multiregion_case(request, cancel_check=cancel_check)
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        return {"status": "blocked", "message": "Multi-region case directory must be empty to prevent stale input reuse."}
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        return {"status": "blocked", "message": "Multi-region case directory must not be a symbolic link."}
    _cancel(cancel_check)
    region_properties = "regions\n(\n    solid\n    (\n" + "".join(f"        {item['id']}\n" for item in case["regions"] if item["kind"] == "solid") + "    )\n    fluid\n    (\n" + "".join(f"        {item['id']}\n" for item in case["regions"] if item["kind"] == "fluid") + "    )\n);\n"
    _write(root, "constant/regionProperties", region_properties)
    _write(root, "constant/spike-materials.json", json.dumps(case["materials"], sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    _write(root, "constant/spike-interfaces.json", json.dumps(case["interfaces"], sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    _write(root, "constant/spike-environment.json", json.dumps({"environment": case["environment"], "heat_sources": case["heat_sources"], "fans": case["fans"], "heatsinks": case["heatsinks"]}, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    _write(root, "README.SPIKE-NOT-RUNNABLE.txt", "NOT-RUNNABLE: this is an evidence-bound multi-region translation manifest, not an executable OpenFOAM case.\nA validated mesh/boundary translator and numerical qualification are required before chtMultiRegionFoam execution.\n")
    _cancel(cancel_check)
    manifest = {**case, "request_digest": _digest(request), "files": _file_digests(root)}
    _write(root, "spike_multiregion_case.json", json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    return {"status": "prepared_not_runnable", "case_dir": str(root), "manifest": manifest}


__all__ = ["ADAPTER_CONTRACT", "ADAPTER_VERSION", "CASE_CONTRACT", "RUNNABLE_CASE_CONTRACT", "MultiRegionOpenFoamError", "REQUEST_CONTRACT", "compile_multiregion_case", "poly_mesh_digest", "prepare_multiregion_case", "prepare_runnable_multiregion_case"]
