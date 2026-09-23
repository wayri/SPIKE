"""Versioned, solver-neutral cross-domain environment profiles.

Environment profiles are explicit solver inputs shared by PI, SI, thermal, and
EMI workflows.  Built-in profiles are inspectable engineering seeds, not
certification evidence.  Validation checks input completeness and consistency;
it never infers qualification, compliance, or certification.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence


ENVIRONMENT_PROFILE_CONTRACT = "spike/environment-profile/v1"
ENVIRONMENT_PROFILE_VALIDATION_CONTRACT = "spike/environment-profile-validation/v1"

SUPPORTED_DOMAINS = ("pi", "si", "thermal", "emi")
ENVIRONMENT_CLASSES = ("standard_lab_ambient_air", "sealed_potted", "automotive", "marine",
                       "aerospace_altitude", "vacuum_space", "user_defined")

_GENERATED_AT = "2026-08-09T00:00:00Z"
_AIR_SOURCE_ID = "spike-nominal-air-seed-v1"
_PROFILE_SOURCE_ID = "spike-environment-profile-seeds-v1"


class EnvironmentProfileError(ValueError):
    """Raised when a requested built-in profile does not exist."""


def _issue(
    code: str,
    severity: str,
    message: str,
    path: str = "",
    suggestion: str = "",
    domains: Iterable[str] = (),
) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "path": path,
        "suggestion": suggestion,
        "domains": list(domains),
        "status": "open",
    }


def _source(source_id: str, title: str, scope: str) -> Dict[str, str]:
    return {
        "id": source_id,
        "kind": "engineering_seed",
        "title": title,
        "publisher": "SPIKE project",
        "locator": "docs/ENVIRONMENT_PROFILES.md",
        "revision_or_date": "2026-08-09",
        "scope": scope,
    }


def _physical(
    *,
    ambient_temperature_k: float | None,
    initial_temperature_k: float | None,
    pressure_pa: float | None,
    relative_humidity: float | None,
    altitude_m: float | None,
    gravity_m_s2: Sequence[float] | None,
    atmosphere_medium: str,
    flow_regime: str,
    velocity_m_s: Sequence[float] | None,
    density_kg_m3: float | None,
    dynamic_viscosity_pa_s: float | None,
    specific_heat_capacity_j_kg_k: float | None,
    thermal_conductivity_w_m_k: float | None,
    volumetric_expansion_per_k: float | None,
    convection_model: str,
    heat_transfer_coefficient_w_m2_k: float | None,
    enclosure_kind: str,
    radiation_enabled: bool,
    radiative_sink_temperature_k: float | None,
    default_surface_emissivity: float | None,
    encapsulation: Mapping[str, Any] | None = None,
    electromagnetic: Mapping[str, Any] | None = None,
    exposure: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "thermal": {
            "ambient_temperature_k": ambient_temperature_k,
            "initial_temperature_k": initial_temperature_k,
            "radiation_enabled": radiation_enabled,
            "radiative_sink_temperature_k": radiative_sink_temperature_k,
            "external_radiative_flux_w_m2": 0.0,
            "default_surface_emissivity": default_surface_emissivity,
        },
        "atmosphere": {
            "medium": atmosphere_medium,
            "pressure_pa": pressure_pa,
            "relative_humidity": relative_humidity,
            "altitude_m": altitude_m,
            "gravity_m_s2": list(gravity_m_s2) if gravity_m_s2 is not None else None,
        },
        "flow": {
            "regime": flow_regime,
            "velocity_m_s": list(velocity_m_s) if velocity_m_s is not None else None,
            "mass_flow_rate_kg_s": None,
            "turbulence_intensity": None,
            "characteristic_length_m": None,
        },
        "fluid": {
            "name": "vacuum" if atmosphere_medium == "vacuum" else "nominal air",
            "density_kg_m3": density_kg_m3,
            "dynamic_viscosity_pa_s": dynamic_viscosity_pa_s,
            "specific_heat_capacity_j_kg_k": specific_heat_capacity_j_kg_k,
            "thermal_conductivity_w_m_k": thermal_conductivity_w_m_k,
            "volumetric_thermal_expansion_per_k": volumetric_expansion_per_k,
        },
        "convection": {
            "model": convection_model,
            "heat_transfer_coefficient_w_m2_k": heat_transfer_coefficient_w_m2_k,
        },
        "enclosure": {
            "kind": enclosure_kind,
            "wall_temperature_k": None,
            "internal_volume_m3": None,
        },
        "encapsulation": {
            "enabled": False,
            "material_name": None,
            "coverage_fraction": 0.0,
            "thickness_m": None,
            "thermal_conductivity_w_m_k": None,
            "density_kg_m3": None,
            "specific_heat_capacity_j_kg_k": None,
            "relative_permittivity": None,
            "loss_tangent": None,
            **dict(encapsulation or {}),
        },
        "electromagnetic": {
            "background_material": "vacuum" if atmosphere_medium == "vacuum" else "nominal air",
            "relative_permittivity": 1.0 if atmosphere_medium == "vacuum" else 1.0006,
            "relative_permeability": 1.0,
            "electrical_conductivity_s_m": 0.0,
            "loss_tangent": 0.0,
            "valid_frequency_min_hz": 0.0,
            "valid_frequency_max_hz": 100.0e9,
            **dict(electromagnetic or {}),
        },
        "electrical": {
            "conductor_reference_temperature_k": ambient_temperature_k,
            "copper_temperature_coefficient_per_k": 0.00393,
        },
        "exposure": {
            "salinity_mass_fraction": 0.0,
            "surface_contamination_conductance_s": None,
            "solar_flux_w_m2": 0.0,
            "ionizing_dose_rate_gy_s": None,
            "atomic_oxygen_flux_m2_s": None,
            "vibration_rms_acceleration_m_s2": None,
            "shock_peak_acceleration_m_s2": None,
            **dict(exposure or {}),
        },
    }


def _profile(
    profile_id: str,
    name: str,
    environment_class: str,
    description: str,
    physical: Dict[str, Any],
    *,
    temperature_range_k: Sequence[float] | None,
    pressure_range_pa: Sequence[float] | None,
    frequency_range_hz: Sequence[float] | None,
    assumptions: Sequence[str],
    known_limitations: Sequence[str],
    required_overrides: Sequence[str] = (),
    origin: str = "spike_builtin",
    input_status: str = "template",
) -> Dict[str, Any]:
    sources = [
        _source(
            _PROFILE_SOURCE_ID,
            "SPIKE cross-domain environment profile engineering seeds",
            "Profile topology, representative operating points, and explicit validity limits.",
        )
    ]
    if physical.get("atmosphere", {}).get("medium") == "air":
        sources.append(_source(
            _AIR_SOURCE_ID,
            "SPIKE nominal dry-air property seed",
            "Representative air properties at the profile operating point; not a substitute for a temperature-dependent material model.",
        ))
    return {
        "contract": ENVIRONMENT_PROFILE_CONTRACT,
        "profile_id": profile_id,
        "name": name,
        "revision": "1.0.0",
        "environment_class": environment_class,
        "description": description,
        "physical": physical,
        "validity": {
            "input_status": input_status,
            "applicable_domains": list(SUPPORTED_DOMAINS),
            "temperature_range_k": list(temperature_range_k) if temperature_range_k else None,
            "pressure_range_pa": list(pressure_range_pa) if pressure_range_pa else None,
            "frequency_range_hz": list(frequency_range_hz) if frequency_range_hz else None,
            "assumptions": list(assumptions),
            "known_limitations": list(known_limitations),
            "required_overrides": list(required_overrides),
            "certification_claimed": False,
            "certification_basis": [],
        },
        "provenance": {
            "origin": origin,
            "profile_revision": "1.0.0",
            "generated_by": "SPIKE environment profile subsystem",
            "generated_at": _GENERATED_AT,
            "sources": sources,
            "parameter_sources": {
                "/physical": [source["id"] for source in sources],
                "/validity": [_PROFILE_SOURCE_ID],
            },
            "transformations": [],
        },
    }


def _air_profile_physical(
    point: Sequence[float | None],
    *,
    enclosure_kind: str = "open",
    flow_regime: str = "still",
    radiation_enabled: bool = False,
    encapsulation: Mapping[str, Any] | None = None,
    exposure: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    temperature, pressure, humidity, altitude, gravity_z, density, viscosity, heat_capacity, conductivity = point
    return _physical(
        ambient_temperature_k=temperature, initial_temperature_k=temperature,
        pressure_pa=pressure, relative_humidity=humidity, altitude_m=altitude,
        gravity_m_s2=(0.0, 0.0, gravity_z), atmosphere_medium="air",
        flow_regime=flow_regime, velocity_m_s=(0.0, 0.0, 0.0),
        density_kg_m3=density, dynamic_viscosity_pa_s=viscosity,
        specific_heat_capacity_j_kg_k=heat_capacity, thermal_conductivity_w_m_k=conductivity,
        volumetric_expansion_per_k=1.0 / float(temperature), convection_model="natural",
        heat_transfer_coefficient_w_m2_k=None, enclosure_kind=enclosure_kind,
        radiation_enabled=radiation_enabled, radiative_sink_temperature_k=temperature,
        default_surface_emissivity=0.80 if radiation_enabled else None,
        encapsulation=encapsulation, exposure=exposure,
    )


_AIR_PROFILE_SEEDS: Sequence[Dict[str, Any]] = (
    {
        "identity": ("standard-lab-air", "Standard lab / ambient air", "standard_lab_ambient_air"),
        "description": "Open laboratory air at a nominal 25 C and one atmosphere.",
        "point": (298.15, 101325.0, 0.50, 0.0, -9.80665, 1.184, 1.849e-5, 1007.0, 0.02551),
        "ranges": ((288.15, 308.15), (90000.0, 110000.0), (0.0, 100.0e9)),
        "options": {},
        "assumptions": ("Nominal dry-air properties are held constant at the operating point.", "The open boundary is not a model of a specific chamber or bench ground plane."),
        "limitations": ("Humidity effects on material surfaces and corona are not derived from relative humidity alone.", "Natural-convection coefficients remain solver outputs, not profile constants."),
    },
    {
        "identity": ("sealed-potted", "Sealed / potted electronics", "sealed_potted"),
        "description": "A sealed enclosure with a fully encapsulated assembly and stagnant internal air.",
        "point": (298.15, 101325.0, 0.20, 0.0, -9.80665, 1.184, 1.849e-5, 1007.0, 0.02551),
        "ranges": ((233.15, 398.15), (50000.0, 150000.0), (0.0, 10.0e9)),
        "options": {"enclosure_kind": "sealed", "flow_regime": "sealed", "encapsulation": {
            "enabled": True, "material_name": "generic epoxy engineering seed", "coverage_fraction": 1.0,
            "thickness_m": 0.005, "thermal_conductivity_w_m_k": 0.8, "density_kg_m3": 1200.0,
            "specific_heat_capacity_j_kg_k": 1000.0, "relative_permittivity": 3.8, "loss_tangent": 0.02,
        }},
        "assumptions": ("Encapsulation is homogeneous, void-free, and in perfect geometric contact unless a solver setup says otherwise.", "The listed epoxy properties are generic seed values and must be replaced for product decisions."),
        "limitations": ("Cure state, filler orientation, voids, interface resistance, and frequency dispersion are not represented.", "A sealed enclosure still requires explicit exterior boundary geometry in a CFD or thermal solve."),
    },
    {
        "identity": ("automotive", "Automotive elevated-temperature air", "automotive"),
        "description": "Representative elevated-temperature automotive air operating point at 85 C.",
        "point": (358.15, 101325.0, 0.20, 0.0, -9.80665, 0.986, 2.13e-5, 1009.0, 0.0300),
        "ranges": ((233.15, 398.15), (70000.0, 110000.0), (0.0, 100.0e9)),
        "options": {"radiation_enabled": True, "exposure": {"vibration_rms_acceleration_m_s2": None, "shock_peak_acceleration_m_s2": None}},
        "assumptions": ("The operating point is not tied to an under-hood, cabin, chassis, or powertrain mounting class.", "Air properties are constant and exclude vehicle motion and fan flow."),
        "limitations": ("Thermal cycling, vibration, shock, fluids, contamination, and load-dump requirements need separate explicit inputs.", "This profile does not imply conformance to any automotive standard or OEM requirement."),
    },
    {
        "identity": ("marine", "Marine humid air", "marine"),
        "description": "Representative warm, high-humidity marine air operating point.",
        "point": (308.15, 101325.0, 0.95, 0.0, -9.80665, 1.145, 1.90e-5, 1010.0, 0.0265),
        "ranges": ((273.15, 333.15), (80000.0, 110000.0), (0.0, 100.0e9)),
        "options": {"radiation_enabled": True, "exposure": {"salinity_mass_fraction": 0.0, "surface_contamination_conductance_s": None}},
        "assumptions": ("The gas phase is humid air; bulk seawater is not present in the CFD domain.", "Salt exposure is not converted into surface conductivity without a measured contamination model."),
        "limitations": ("Salt fog, condensation, corrosion, coating degradation, and creepage effects are not inferred.", "This profile does not imply marine equipment qualification or certification."),
    },
    {
        "identity": ("aerospace-altitude", "Aerospace / altitude air", "aerospace_altitude"),
        "description": "Representative low-pressure air operating point near 10 km geometric altitude.",
        "point": (223.15, 26436.0, 0.0, 10000.0, -9.776, 0.4135, 1.46e-5, 1005.0, 0.0200),
        "ranges": ((193.15, 333.15), (1000.0, 110000.0), (0.0, 100.0e9)),
        "options": {"radiation_enabled": True},
        "assumptions": ("Pressure, temperature, and density are an explicit point, not an automatic atmosphere model.", "No aircraft velocity, ram-air flow, pressurization schedule, or compartment is implied."),
        "limitations": ("Corona, partial discharge, Paschen behavior, decompression, vibration, and radiation require separate models.", "This profile does not imply aerospace qualification or airworthiness compliance."),
    },
)


def _build_profiles() -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = {}
    for seed in _AIR_PROFILE_SEEDS:
        profile_id, name, environment_class = seed["identity"]
        temperature_range, pressure_range, frequency_range = seed["ranges"]
        profiles[profile_id] = _profile(
            profile_id, name, environment_class, seed["description"],
            _air_profile_physical(seed["point"], **seed["options"]),
            temperature_range_k=temperature_range, pressure_range_pa=pressure_range,
            frequency_range_hz=frequency_range, assumptions=seed["assumptions"],
            known_limitations=seed["limitations"],
        )

    profiles["vacuum-space"] = _profile(
        "vacuum-space", "Vacuum / space", "vacuum_space",
        "Rarefied environment with convection disabled and radiative heat transfer enabled.",
        _physical(
            ambient_temperature_k=293.15, initial_temperature_k=293.15, pressure_pa=1.0e-3,
            relative_humidity=0.0, altitude_m=None, gravity_m_s2=(0.0, 0.0, 0.0),
            atmosphere_medium="vacuum", flow_regime="vacuum", velocity_m_s=(0.0, 0.0, 0.0),
            density_kg_m3=0.0, dynamic_viscosity_pa_s=0.0, specific_heat_capacity_j_kg_k=0.0,
            thermal_conductivity_w_m_k=0.0, volumetric_expansion_per_k=0.0,
            convection_model="disabled", heat_transfer_coefficient_w_m2_k=0.0,
            enclosure_kind="free_space", radiation_enabled=True, radiative_sink_temperature_k=3.0,
            default_surface_emissivity=0.80,
            electromagnetic={"background_material": "vacuum", "relative_permittivity": 1.0,
                "relative_permeability": 1.0, "electrical_conductivity_s_m": 0.0, "loss_tangent": 0.0,
                "valid_frequency_min_hz": 0.0, "valid_frequency_max_hz": 1.0e12},
            exposure={"solar_flux_w_m2": 0.0, "ionizing_dose_rate_gy_s": None, "atomic_oxygen_flux_m2_s": None},
        ),
        temperature_range_k=(2.7, 423.15), pressure_range_pa=(1.0e-10, 100.0),
        frequency_range_hz=(0.0, 1.0e12),
        assumptions=("Continuum convection is disabled; conduction through solids and contacts remains available.", "The 3 K sink and zero flux are seed values, not an orbital thermal environment."),
        known_limitations=("Orbit, attitude, eclipse, optical properties, charging, and radiation need explicit inputs.", "Outgassing, plasma, atomic oxygen, and mission qualification are not inferred."),
    )

    profiles["user-defined"] = _profile(
        "user-defined", "User-defined environment", "user_defined",
        "Blank profile requiring explicit physical inputs and provenance.",
        _physical(
            ambient_temperature_k=None, initial_temperature_k=None, pressure_pa=None,
            relative_humidity=None, altitude_m=None, gravity_m_s2=None,
            atmosphere_medium="user_defined", flow_regime="user_defined", velocity_m_s=None,
            density_kg_m3=None, dynamic_viscosity_pa_s=None, specific_heat_capacity_j_kg_k=None,
            thermal_conductivity_w_m_k=None, volumetric_expansion_per_k=None,
            convection_model="user_defined", heat_transfer_coefficient_w_m2_k=None,
            enclosure_kind="user_defined", radiation_enabled=False,
            radiative_sink_temperature_k=None, default_surface_emissivity=None,
            electromagnetic={"background_material": "user defined", "relative_permittivity": None,
                "relative_permeability": None, "electrical_conductivity_s_m": None, "loss_tangent": None,
                "valid_frequency_min_hz": None, "valid_frequency_max_hz": None},
        ),
        temperature_range_k=None, pressure_range_pa=None, frequency_range_hz=None,
        assumptions=(), known_limitations=("No physical behavior is implied until required inputs are supplied and reviewed.",),
        required_overrides=(
            "/physical/thermal/ambient_temperature_k", "/physical/thermal/initial_temperature_k",
            "/physical/atmosphere/pressure_pa", "/physical/atmosphere/gravity_m_s2",
            "/physical/electromagnetic/relative_permittivity", "/physical/electromagnetic/relative_permeability",
            "/physical/electromagnetic/electrical_conductivity_s_m", "/physical/electromagnetic/loss_tangent",
        ),
        origin="user", input_status="draft",
    )
    return profiles


_BUILTIN_PROFILES = _build_profiles()


def list_environment_profiles() -> List[Dict[str, Any]]:
    """Return stable summaries for all built-in profiles."""
    return [
        {
            "profile_id": profile["profile_id"],
            "name": profile["name"],
            "environment_class": profile["environment_class"],
            "revision": profile["revision"],
            "description": profile["description"],
        }
        for profile in _BUILTIN_PROFILES.values()
    ]


def get_environment_profile(profile_id: str) -> Dict[str, Any]:
    """Return a deep copy of a built-in profile."""
    key = str(profile_id).strip().lower()
    try:
        return deepcopy(_BUILTIN_PROFILES[key])
    except KeyError as exc:
        raise EnvironmentProfileError(f"Unknown environment profile: {profile_id!r}") from exc


def _deep_merge(base: Dict[str, Any], overrides: Mapping[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def materialize_environment_profile(
    profile_id: str,
    overrides: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Copy a preset and apply explicit recursive overrides without mutation."""
    profile = get_environment_profile(profile_id)
    if overrides:
        profile = _deep_merge(profile, overrides)
        profile["provenance"].setdefault("transformations", []).append({
            "kind": "explicit_override",
            "paths": sorted(_flatten_paths(overrides)),
        })
    return profile


def create_user_defined_profile(
    profile_id: str,
    name: str,
    physical_overrides: Mapping[str, Any] | None = None,
    *,
    source_title: str = "User-supplied environment inputs",
    source_locator: str = "",
) -> Dict[str, Any]:
    """Create a user-owned profile from the blank versioned template."""
    profile = get_environment_profile("user-defined")
    profile["profile_id"] = str(profile_id).strip()
    profile["name"] = str(name).strip()
    if physical_overrides:
        profile["physical"] = _deep_merge(profile["physical"], physical_overrides)
    user_source = {
        "id": "user-source-1",
        "kind": "user_supplied",
        "title": source_title,
        "publisher": "",
        "locator": source_locator,
        "revision_or_date": "",
        "scope": "User-supplied profile values; review and uncertainty remain the user's responsibility.",
    }
    profile["provenance"].update({
        "origin": "user",
        "sources": [user_source],
        "parameter_sources": {"/physical": [user_source["id"]]},
        "transformations": [],
    })
    return profile


def _flatten_paths(value: Mapping[str, Any], prefix: str = "") -> List[str]:
    paths: List[str] = []
    for key, item in value.items():
        path = f"{prefix}/{key}"
        if isinstance(item, Mapping):
            paths.extend(_flatten_paths(item, path))
        else:
            paths.append(path)
    return paths


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _path_value(profile: Mapping[str, Any], path: str) -> Any:
    value: Any = profile
    for part in path.strip("/").split("/"):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _require_number(
    profile: Mapping[str, Any],
    path: str,
    issues: List[Dict[str, Any]],
    domains: Sequence[str],
    *,
    minimum: float | None = None,
    exclusive_minimum: bool = False,
) -> float | None:
    value = _finite_number(_path_value(profile, path))
    invalid = value is None
    if value is not None and minimum is not None:
        invalid = value <= minimum if exclusive_minimum else value < minimum
    if invalid:
        qualifier = "positive " if minimum == 0 and exclusive_minimum else "finite "
        issues.append(_issue(
            "ENV_PHYSICAL_INPUT_REQUIRED",
            "error",
            f"{path} must be a {qualifier}SI value for {', '.join(domains)}.",
            path,
            "Supply a traceable value appropriate to the actual operating condition.",
            domains,
        ))
        return None
    return value


def _validate_range(
    profile: Mapping[str, Any],
    value_path: str,
    range_path: str,
    issues: List[Dict[str, Any]],
) -> None:
    value = _finite_number(_path_value(profile, value_path))
    limits = _path_value(profile, range_path)
    if value is None or limits is None:
        return
    if not isinstance(limits, list) or len(limits) != 2:
        issues.append(_issue("ENV_VALIDITY_RANGE_INVALID", "error", f"{range_path} must have two ordered values.", range_path))
        return
    low, high = (_finite_number(item) for item in limits)
    if low is None or high is None or low > high:
        issues.append(_issue("ENV_VALIDITY_RANGE_INVALID", "error", f"{range_path} must have two ordered finite values.", range_path))
    elif not low <= value <= high:
        issues.append(_issue(
            "ENV_OPERATING_POINT_OUTSIDE_VALIDITY",
            "error",
            f"{value_path}={value:g} is outside the declared range [{low:g}, {high:g}].",
            value_path,
            "Change the operating point or provide a defensible wider validity range and provenance.",
            SUPPORTED_DOMAINS,
        ))


def _validate_vector(profile: Mapping[str, Any], path: str, issues: List[Dict[str, Any]], domains: Sequence[str]) -> None:
    value = _path_value(profile, path)
    if not isinstance(value, list) or len(value) != 3 or any(_finite_number(item) is None for item in value):
        issues.append(_issue(
            "ENV_VECTOR_REQUIRED",
            "error",
            f"{path} must contain three finite SI components.",
            path,
            domains=domains,
        ))


def _validate_provenance(profile: Mapping[str, Any], issues: List[Dict[str, Any]]) -> None:
    provenance = profile.get("provenance")
    if not isinstance(provenance, Mapping):
        issues.append(_issue("ENV_PROVENANCE_MISSING", "error", "Profile provenance is required.", "/provenance"))
        return
    sources = provenance.get("sources")
    if not isinstance(sources, list) or not sources:
        issues.append(_issue("ENV_PROVENANCE_SOURCE_MISSING", "error", "At least one provenance source is required.", "/provenance/sources"))
        return
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            issues.append(_issue("ENV_PROVENANCE_SOURCE_INVALID", "error", "Each provenance source must be an object.", f"/provenance/sources/{index}"))
            continue
        source_id = str(source.get("id", "")).strip()
        if not source_id or not str(source.get("kind", "")).strip() or not str(source.get("title", "")).strip():
            issues.append(_issue("ENV_PROVENANCE_SOURCE_INCOMPLETE", "error", "Each source requires id, kind, and title.", f"/provenance/sources/{index}"))
        source_ids.add(source_id)
    parameter_sources = provenance.get("parameter_sources")
    if not isinstance(parameter_sources, Mapping) or not parameter_sources:
        issues.append(_issue("ENV_PARAMETER_PROVENANCE_MISSING", "warning", "No parameter-to-source mapping is recorded.", "/provenance/parameter_sources"))
    else:
        referenced = {
            str(source_id)
            for ids in parameter_sources.values()
            if isinstance(ids, list)
            for source_id in ids
        }
        unknown = sorted(referenced - source_ids)
        if unknown:
            issues.append(_issue("ENV_PROVENANCE_REFERENCE_UNKNOWN", "error", f"Unknown provenance source id(s): {', '.join(unknown)}.", "/provenance/parameter_sources"))


def validate_environment_profile(
    profile: Mapping[str, Any],
    requested_domains: Sequence[str] = SUPPORTED_DOMAINS,
) -> Dict[str, Any]:
    """Validate physical completeness and consistency for requested domains.

    ``can_supply_solver_inputs`` only means that required fields are present and
    internally consistent.  It is not a solver-validation, qualification, or
    certification result.
    """
    domains: List[str] = []
    issues: List[Dict[str, Any]] = []
    for raw_domain in requested_domains:
        domain = str(raw_domain).strip().lower()
        if domain not in SUPPORTED_DOMAINS:
            issues.append(_issue("ENV_DOMAIN_UNSUPPORTED", "error", f"Unsupported domain: {raw_domain!r}.", "/requested_domains"))
        elif domain not in domains:
            domains.append(domain)
    if not domains:
        issues.append(_issue("ENV_DOMAIN_REQUIRED", "error", "At least one supported domain is required.", "/requested_domains"))

    if not isinstance(profile, Mapping):
        issues.append(_issue("ENV_PROFILE_INVALID", "error", "Environment profile must be an object.", "/"))
        return _validation_result({}, domains, issues)

    if profile.get("contract") != ENVIRONMENT_PROFILE_CONTRACT:
        issues.append(_issue("ENV_CONTRACT_UNSUPPORTED", "error", f"Expected {ENVIRONMENT_PROFILE_CONTRACT}.", "/contract"))
    if not str(profile.get("profile_id", "")).strip():
        issues.append(_issue("ENV_PROFILE_ID_REQUIRED", "error", "profile_id is required.", "/profile_id"))
    if not str(profile.get("name", "")).strip():
        issues.append(_issue("ENV_PROFILE_NAME_REQUIRED", "error", "name is required.", "/name"))
    if profile.get("environment_class") not in ENVIRONMENT_CLASSES:
        issues.append(_issue("ENV_CLASS_UNSUPPORTED", "error", "Select a supported environment class.", "/environment_class"))

    validity = profile.get("validity") if isinstance(profile.get("validity"), Mapping) else {}
    if validity.get("certification_claimed") is not False or validity.get("certification_basis"):
        issues.append(_issue(
            "ENV_CERTIFICATION_CLAIM_FORBIDDEN",
            "error",
            "An environment input profile cannot claim or infer certification.",
            "/validity/certification_claimed",
            "Record qualification evidence in a separate reviewed verification artifact.",
            domains,
        ))
    applicable = validity.get("applicable_domains")
    if not isinstance(applicable, list):
        issues.append(_issue("ENV_APPLICABILITY_REQUIRED", "error", "validity.applicable_domains must be explicit.", "/validity/applicable_domains"))
    else:
        excluded = [domain for domain in domains if domain not in applicable]
        if excluded:
            issues.append(_issue("ENV_DOMAIN_OUTSIDE_APPLICABILITY", "error", f"Profile does not declare applicability for: {', '.join(excluded)}.", "/validity/applicable_domains", domains=excluded))

    physical = profile.get("physical")
    if not isinstance(physical, Mapping):
        issues.append(_issue("ENV_PHYSICAL_INPUTS_MISSING", "error", "physical inputs are required.", "/physical", domains=domains))
        return _validation_result(profile, domains, issues)

    common_domains = [domain for domain in domains if domain in SUPPORTED_DOMAINS]
    _require_number(profile, "/physical/thermal/ambient_temperature_k", issues, common_domains, minimum=0.0, exclusive_minimum=True)
    _require_number(profile, "/physical/thermal/initial_temperature_k", issues, common_domains, minimum=0.0, exclusive_minimum=True)
    _require_number(profile, "/physical/atmosphere/pressure_pa", issues, common_domains, minimum=0.0, exclusive_minimum=True)
    _validate_vector(profile, "/physical/atmosphere/gravity_m_s2", issues, common_domains)

    humidity = _finite_number(_path_value(profile, "/physical/atmosphere/relative_humidity"))
    medium = str(_path_value(profile, "/physical/atmosphere/medium") or "")
    if medium != "vacuum" and (humidity is None or not 0.0 <= humidity <= 1.0):
        issues.append(_issue("ENV_HUMIDITY_INVALID", "error", "Relative humidity must be a fraction from 0 to 1.", "/physical/atmosphere/relative_humidity", domains=common_domains))

    if "pi" in domains:
        _require_number(profile, "/physical/electrical/conductor_reference_temperature_k", issues, ("pi",), minimum=0.0, exclusive_minimum=True)
        _require_number(profile, "/physical/electrical/copper_temperature_coefficient_per_k", issues, ("pi",), minimum=0.0)

    for domain in ("si", "emi"):
        if domain not in domains:
            continue
        _require_number(profile, "/physical/electromagnetic/relative_permittivity", issues, (domain,), minimum=0.0, exclusive_minimum=True)
        _require_number(profile, "/physical/electromagnetic/relative_permeability", issues, (domain,), minimum=0.0, exclusive_minimum=True)
        _require_number(profile, "/physical/electromagnetic/electrical_conductivity_s_m", issues, (domain,), minimum=0.0)
        _require_number(profile, "/physical/electromagnetic/loss_tangent", issues, (domain,), minimum=0.0)
        low = _require_number(profile, "/physical/electromagnetic/valid_frequency_min_hz", issues, (domain,), minimum=0.0)
        high = _require_number(profile, "/physical/electromagnetic/valid_frequency_max_hz", issues, (domain,), minimum=0.0, exclusive_minimum=True)
        if low is not None and high is not None and low >= high:
            issues.append(_issue("ENV_EM_FREQUENCY_RANGE_INVALID", "error", "Electromagnetic frequency limits must be ordered.", "/physical/electromagnetic", domains=(domain,)))

        encapsulation = _path_value(profile, "/physical/encapsulation")
        if isinstance(encapsulation, Mapping) and encapsulation.get("enabled"):
            _require_number(profile, "/physical/encapsulation/relative_permittivity", issues, (domain,), minimum=0.0, exclusive_minimum=True)
            _require_number(profile, "/physical/encapsulation/loss_tangent", issues, (domain,), minimum=0.0)

    if "thermal" in domains:
        convection_model = str(_path_value(profile, "/physical/convection/model") or "")
        flow_regime = str(_path_value(profile, "/physical/flow/regime") or "")
        _validate_vector(profile, "/physical/flow/velocity_m_s", issues, ("thermal",))
        if medium == "vacuum":
            if convection_model != "disabled" or flow_regime != "vacuum":
                issues.append(_issue("ENV_VACUUM_CONVECTION_FORBIDDEN", "error", "Vacuum profiles must disable continuum convection and airflow.", "/physical/convection/model", domains=("thermal",)))
            velocity = _path_value(profile, "/physical/flow/velocity_m_s")
            if isinstance(velocity, list) and any(abs(float(item)) > 0 for item in velocity if _finite_number(item) is not None):
                issues.append(_issue("ENV_VACUUM_FLOW_FORBIDDEN", "error", "Vacuum flow velocity must be zero.", "/physical/flow/velocity_m_s", domains=("thermal",)))
        elif convection_model == "specified_coefficient":
            _require_number(profile, "/physical/convection/heat_transfer_coefficient_w_m2_k", issues, ("thermal",), minimum=0.0, exclusive_minimum=True)
        elif convection_model in {"natural", "forced", "solver_resolved"}:
            for path in (
                "/physical/fluid/density_kg_m3",
                "/physical/fluid/dynamic_viscosity_pa_s",
                "/physical/fluid/specific_heat_capacity_j_kg_k",
                "/physical/fluid/thermal_conductivity_w_m_k",
            ):
                _require_number(profile, path, issues, ("thermal",), minimum=0.0, exclusive_minimum=True)
        elif convection_model != "disabled":
            issues.append(_issue("ENV_CONVECTION_MODEL_UNSUPPORTED", "error", "Select a supported convection model.", "/physical/convection/model", domains=("thermal",)))

        radiation_enabled = _path_value(profile, "/physical/thermal/radiation_enabled")
        if not isinstance(radiation_enabled, bool):
            issues.append(_issue("ENV_RADIATION_FLAG_REQUIRED", "error", "radiation_enabled must be explicit.", "/physical/thermal/radiation_enabled", domains=("thermal",)))
        elif radiation_enabled:
            _require_number(profile, "/physical/thermal/radiative_sink_temperature_k", issues, ("thermal",), minimum=0.0, exclusive_minimum=True)
            emissivity = _require_number(profile, "/physical/thermal/default_surface_emissivity", issues, ("thermal",), minimum=0.0)
            if emissivity is not None and emissivity > 1.0:
                issues.append(_issue("ENV_EMISSIVITY_INVALID", "error", "Surface emissivity must be between 0 and 1.", "/physical/thermal/default_surface_emissivity", domains=("thermal",)))

        encapsulation = _path_value(profile, "/physical/encapsulation")
        if isinstance(encapsulation, Mapping) and encapsulation.get("enabled"):
            coverage = _require_number(profile, "/physical/encapsulation/coverage_fraction", issues, ("thermal",), minimum=0.0, exclusive_minimum=True)
            if coverage is not None and coverage > 1.0:
                issues.append(_issue("ENV_ENCAPSULATION_COVERAGE_INVALID", "error", "Encapsulation coverage must not exceed 1.", "/physical/encapsulation/coverage_fraction", domains=("thermal",)))
            for path in (
                "/physical/encapsulation/thickness_m",
                "/physical/encapsulation/thermal_conductivity_w_m_k",
                "/physical/encapsulation/density_kg_m3",
                "/physical/encapsulation/specific_heat_capacity_j_kg_k",
            ):
                _require_number(profile, path, issues, ("thermal",), minimum=0.0, exclusive_minimum=True)

    _validate_range(profile, "/physical/thermal/ambient_temperature_k", "/validity/temperature_range_k", issues)
    _validate_range(profile, "/physical/atmosphere/pressure_pa", "/validity/pressure_range_pa", issues)
    _validate_provenance(profile, issues)

    required_overrides = validity.get("required_overrides")
    if not isinstance(required_overrides, list):
        issues.append(_issue("ENV_REQUIRED_OVERRIDES_INVALID", "error", "required_overrides must be a list of JSON-pointer paths.", "/validity/required_overrides"))
    else:
        unresolved = [path for path in required_overrides if _path_value(profile, str(path)) is None]
        if unresolved:
            issues.append(_issue(
                "ENV_REQUIRED_OVERRIDES_UNRESOLVED",
                "error",
                f"{len(unresolved)} required physical override(s) remain unresolved.",
                "/validity/required_overrides",
                "Supply values and provenance for every listed path.",
                domains,
            ))

    if validity.get("input_status") in {"draft", "template"}:
        issues.append(_issue(
            "ENV_ENGINEERING_INPUT_REVIEW_REQUIRED",
            "warning",
            "This profile contains draft or template engineering inputs and requires project-specific review.",
            "/validity/input_status",
            "Confirm operating points, property sources, uncertainty, and geometry-specific boundaries before solving.",
            domains,
        ))

    return _validation_result(profile, domains, issues)


def _validation_result(
    profile: Mapping[str, Any],
    domains: Sequence[str],
    issues: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    domain_readiness: Dict[str, Dict[str, Any]] = {}
    global_errors = [item for item in issues if item.get("severity") == "error" and not item.get("domains")]
    for domain in domains:
        relevant_errors = [
            item for item in issues
            if item.get("severity") == "error" and (not item.get("domains") or domain in item.get("domains", []))
        ]
        domain_readiness[domain] = {
            "inputs_complete": not relevant_errors,
            "blocking_issue_codes": sorted({str(item.get("code")) for item in relevant_errors}),
        }
    has_errors = bool(global_errors) or any(not item["inputs_complete"] for item in domain_readiness.values())
    review_required = any(item.get("severity") == "warning" for item in issues)
    return {
        "contract": ENVIRONMENT_PROFILE_VALIDATION_CONTRACT,
        "profile_contract": profile.get("contract") if isinstance(profile, Mapping) else None,
        "profile_id": profile.get("profile_id") if isinstance(profile, Mapping) else None,
        "status": "invalid" if has_errors else "review_required" if review_required else "ready",
        "requested_domains": list(domains),
        "can_supply_solver_inputs": bool(domains) and not has_errors,
        "domain_readiness": domain_readiness,
        "issues": [dict(item) for item in issues],
        "certification": {
            "status": "not_assessed",
            "claimed": False,
            "statement": "Environment input validation is not qualification, compliance, or certification.",
        },
    }


__all__ = [
    "ENVIRONMENT_CLASSES",
    "ENVIRONMENT_PROFILE_CONTRACT",
    "ENVIRONMENT_PROFILE_VALIDATION_CONTRACT",
    "EnvironmentProfileError",
    "SUPPORTED_DOMAINS",
    "create_user_defined_profile",
    "get_environment_profile",
    "list_environment_profiles",
    "materialize_environment_profile",
    "validate_environment_profile",
]
