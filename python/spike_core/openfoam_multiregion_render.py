"""Render admitted multi-region data into OpenFOAM dictionary files.

Kept separate from request and mesh admission so the public translation module
remains a bounded orchestration surface. This module is private implementation
detail; public APIs continue to live in ``openfoam_multiregion``.
"""

from __future__ import annotations

import math
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from .openfoam_multiregion import (
    MultiRegionOpenFoamError,
    _boundary_field,
    _boundary_radiation_properties,
    _finite,
    _foam_file,
    _fv_options,
    _fv_schemes,
    _radiation_properties,
    _thermophysical_properties,
    _view_factors_dict,
    _write,
)


def write_runnable_dictionaries(
    case: Mapping[str, Any],
    meshes: Mapping[str, Mapping[str, Any]],
    root: Path,
) -> None:
    """Write the v2606 region dictionary tree for an already admitted case."""
    material_map = {item["id"]: item for item in case["materials"]}
    from .openfoam_turbulence import field_bodies, turbulence_dictionary, turbulence_schemes, turbulence_solution, yplus_observers
    turbulence_model = case['environment'].get('turbulence_model')
    for interface in case["interfaces"]:
        if interface["kind"] != "thermal_contact":
            interface["openfoam_baffle"] = {}
            continue
        baffle = interface.get("openfoam_baffle", {})
        if not isinstance(baffle, Mapping):
            raise MultiRegionOpenFoamError(
                f"Interface {interface['id']} openfoam_baffle must be an object."
            )
        thickness = _finite(
            baffle.get("thickness_m"),
            f"interface {interface['id']} baffle thickness_m", positive=True,
        )
        conductivity = _finite(
            baffle.get("conductivity_w_mk"),
            f"interface {interface['id']} baffle conductivity_w_mk", positive=True,
        )
        expected = (
            float(interface["thermal_resistance_k_per_w"])
            * float(interface["contact_area_mm2"]) * 1e-6
        )
        if not math.isclose(
            thickness / conductivity, expected, rel_tol=1e-6, abs_tol=1e-12,
        ):
            raise MultiRegionOpenFoamError(
                f"Interface {interface['id']} baffle layer does not reproduce "
                "its declared contact resistance and area."
            )
        interface["openfoam_baffle"] = {
            "thickness_m": thickness, "conductivity_w_mk": conductivity,
        }
    solid_regions = " ".join(
        item["id"] for item in case["regions"] if item["kind"] == "solid"
    )
    fluid_regions = " ".join(
        item["id"] for item in case["regions"] if item["kind"] == "fluid"
    )
    _write(
        root, "constant/regionProperties",
        _foam_file(
            "dictionary", "regionProperties",
            f"regions\n(\n    solid ({solid_regions})\n    fluid ({fluid_regions})\n);\n",
            location="constant",
        ),
    )
    gravity = case["environment"]["gravity_m_s2"]
    _write(
        root, "constant/g",
        _foam_file(
            "uniformDimensionedVectorField", "g",
            "dimensions [0 1 -2 0 0 0 0];\n"
            f"value ({gravity[0]:.17g} {gravity[1]:.17g} {gravity[2]:.17g});\n",
            location="constant",
        ),
    )
    numerics = case["numerics"]
    has_fluid = any(region["kind"] == "fluid" for region in case["regions"])
    frozen_flow = has_fluid and not bool(case["requested_physics"].get("fluid_flow"))
    root_frozen = "    frozenFlow true;\n" if frozen_flow else ""
    flux_objects = []
    radiation_patches = {
        (item["region_id"], item["patch"])
        for item in case["environment"].get("radiation_model", {}).get("boundaries", [])
    }
    for region in case["regions"]:
        sink_patches = sorted(
            patch for patch, owner in meshes[region["id"]]["ownership"].items()
            if owner == "external:fixed_temperature"
            or (region["id"], patch) in radiation_patches
        )
        if sink_patches:
            flux_objects.append(
                f"    wallHeatFlux_{region['id']}\n    {{\n        type wallHeatFlux;\n"
                "        libs (fieldFunctionObjects);\n"
                f"        region {region['id']};\n        patches ({' '.join(sink_patches)});\n"
                "        executeControl timeStep;\n"
                f"        executeInterval {numerics['validation_interval_steps']};\n"
                "        writeControl timeStep;\n"
                f"        writeInterval {numerics['validation_interval_steps']};\n"
                "        writeToFile true;\n        log true;\n    }"
            )
    if case["fans"] and turbulence_model is None:
        from .openfoam_flow_diagnostics import render_flow_energy_objects
        from .openfoam_mesh_geometry_audit import audit_polymesh_geometry
        open_patches = {region["id"]: sorted(patch for patch, owner in meshes[region["id"]]["ownership"].items()
            if owner.startswith("fan:") or owner == "external:pressure_outlet") for region in case["regions"]}
        # Observations, not promotion: normal-gradient conduction only qualifies
        # on independently verified orthogonal constant-k fixture meshes.
        geometry_audits = {}
        for region in case["regions"]:
            try:
                geometry_audits[region["id"]] = audit_polymesh_geometry(meshes[region["id"]]["poly_mesh"])
            except (ValueError, OSError, OverflowError) as exc:
                geometry_audits[region["id"]] = {"orthogonal_centroid_geometry": False, "error": str(exc)}
        orthogonal = all(item["orthogonal_centroid_geometry"] for item in geometry_audits.values()) and turbulence_model is None
        diagnostics = render_flow_energy_objects({region["id"]: region["kind"] for region in case["regions"]},
            open_patches, orthogonal_constant_k=orthogonal)
        _write(root, "constant/geometryDiagnostic.json", json.dumps({"regions": geometry_audits,
            "orthogonal_constant_k_diagnostic_enabled": orthogonal, "production_qualified": False}, indent=2))
        flux_objects.append(diagnostics["dictionary_entries"])
    from .openfoam_buoyancy import render_buoyancy_observers
    if turbulence_model is not None:
        flux_objects.append(yplus_observers(case))
    try:
        buoyancy_observers = render_buoyancy_observers(case)
    except ValueError as exc:
        raise MultiRegionOpenFoamError(str(exc)) from exc
    if buoyancy_observers:
        flux_objects.append(buoyancy_observers)
    functions = (
        "functions\n{\n" + "\n".join(flux_objects) + "\n}\n"
        if flux_objects else ""
    )
    _write(
        root, "system/controlDict", _foam_file(
            "dictionary", "controlDict",
            "application chtMultiRegionFoam;\nstartFrom startTime;\nstartTime 0;\n"
            f"stopAt endTime;\nendTime {numerics['end_time_s']:.17g};\n"
            f"deltaT {numerics['delta_t_s']:.17g};\nwriteControl timeStep;\n"
            f"writeInterval {numerics['write_interval_steps']};\npurgeWrite 0;\n"
            "writeFormat ascii;\nwritePrecision 10;\nrunTimeModifiable false;\n"
            f"{functions}", location="system",
        ),
    )
    _write(
        root, "system/fvSolution", _foam_file(
            "dictionary", "fvSolution",
            f"PIMPLE\n{{\n    nOuterCorrectors {numerics['outer_correctors']};\n    nCorrectors 1;\n"
            f"{root_frozen}    nNonOrthogonalCorrectors 0;\n}}\n", location="system",
        ),
    )
    _write(
        root, "system/fvSchemes", _foam_file(
            "dictionary", "fvSchemes", "ddtSchemes { default Euler; }\n",
            location="system",
        ),
    )
    # The WSL OpenFOAM launcher rebuilds its command through a shell, where
    # ``grad(T)`` is parsed as syntax. A case-owned alphanumeric alias keeps the
    # external process argv safe while still writing the canonical grad(T)
    # field consumed by the importer.
    _write(
        root, "system/gradT", _foam_file(
            "dictionary", "gradT",
            "type grad;\nlibs (fieldFunctionObjects);\nfield T;\n"
            "executeControl writeTime;\nwriteControl writeTime;\n",
            location="system",
        ),
    )
    for region in case["regions"]:
        region_id = region["id"]
        material = material_map[region["material_id"]]
        target_mesh = root / "constant" / region_id / "polyMesh"
        shutil.copytree(meshes[region_id]["poly_mesh"], target_mesh, symlinks=False)
        thermo_body = (("dpdt true;\n" if case["environment"].get("dpdt_enabled",True) else "dpdt false;\n") if region["kind"] == "fluid" else "") + _thermophysical_properties(material)
        _write(root, f"constant/{region_id}/thermophysicalProperties", _foam_file("dictionary", "thermophysicalProperties", thermo_body, location=f"constant/{region_id}"))
        _write(root, f"constant/{region_id}/radiationProperties", _foam_file("dictionary", "radiationProperties", _radiation_properties(case, region_id), location=f"constant/{region_id}"))
        boundary_radiation = _boundary_radiation_properties(case, region_id)
        if boundary_radiation:
            _write(root, f"constant/{region_id}/boundaryRadiationProperties", _foam_file("dictionary", "boundaryRadiationProperties", boundary_radiation, location=f"constant/{region_id}"))
            _write(root, f"constant/{region_id}/viewFactorsDict", _foam_file("dictionary", "viewFactorsDict", _view_factors_dict(case, region_id), location=f"constant/{region_id}"))
        schemes = _fv_schemes(region['kind'])
        if region['kind'] == 'fluid' and turbulence_model is not None:
            schemes = turbulence_schemes(schemes)
        _write(root, f"system/{region_id}/fvSchemes", _foam_file("dictionary", "fvSchemes", schemes, location=f"system/{region_id}"))
        if region["kind"] == "fluid":
            scalar_solver = "solver PBiCGStab; preconditioner DILU; tolerance 1e-8; relTol 0;"
            frozen_entry = " frozenFlow true;" if frozen_flow else ""
            solution_body = f"solvers\n{{\n    rho {{ solver diagonal; }}\n    rhoFinal {{ $rho; }}\n    p_rgh {{ solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0.05; }}\n    p_rghFinal {{ $p_rgh; relTol 0; }}\n    U {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.05; }}\n    UFinal {{ $U; relTol 0; }}\n    h {{ {scalar_solver} }}\n    hFinal {{ $h; relTol 0; }}\n}}\nPIMPLE {{ nOuterCorrectors {numerics['outer_correctors']}; nCorrectors 1; nNonOrthogonalCorrectors 0; pRefCell 0; pRefValue 0;{frozen_entry} }}\n"
        else:
            scalar_solver = "solver PCG; preconditioner DIC; tolerance 1e-8; relTol 0;"
            solution_body = f"solvers\n{{\n    h {{ {scalar_solver} }}\n    hFinal {{ $h; relTol 0; }}\n}}\nPIMPLE {{ nNonOrthogonalCorrectors 0; }}\n"
        if region['kind'] == 'fluid' and turbulence_model is not None:
            solution_body = turbulence_solution(solution_body)
        _write(root, f"system/{region_id}/fvSolution", _foam_file("dictionary", "fvSolution", solution_body, location=f"system/{region_id}"))
        _write(root, f"system/{region_id}/fvOptions", _foam_file("dictionary", "fvOptions", _fv_options(case, region_id), location=f"system/{region_id}"))
        _write(root, f"0/{region_id}/T", _foam_file("volScalarField", "T", f"dimensions [0 0 0 1 0 0 0];\ninternalField uniform {case['environment']['ambient_temperature_k']};\n" + _boundary_field(case, region, meshes, "T"), location=f"0/{region_id}"))
        _write(root, f"0/{region_id}/p", _foam_file("volScalarField", "p", "dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 101325;\nboundaryField\n{\n" + "\n".join(f"    {patch} {{ type calculated; value uniform 101325; }}" for patch in sorted(meshes[region_id]["patches"])) + "\n}\n", location=f"0/{region_id}"))
        if region["kind"] == "fluid":
            turbulence_body = turbulence_dictionary(turbulence_model)
            _write(root, f"constant/{region_id}/momentumTransport", _foam_file("dictionary", "momentumTransport", turbulence_body, location=f"constant/{region_id}"))
            _write(root, f"constant/{region_id}/turbulenceProperties", _foam_file("dictionary", "turbulenceProperties", turbulence_body, location=f"constant/{region_id}"))
            for field_name, body in field_bodies(turbulence_model, meshes[region_id]['ownership']).items():
                _write(root, f'0/{region_id}/{field_name}', _foam_file('volScalarField',field_name,body,location=f'0/{region_id}'))
            _write(root, f"0/{region_id}/U", _foam_file("volVectorField", "U", "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\n" + _boundary_field(case, region, meshes, "U"), location=f"0/{region_id}"))
            # p_rgh is absolute p minus rho*g*h, not a gauge pressure.
            # At zero gravity, starting at zero against an atmospheric outlet
            # creates an artificial 1-atm impulse in the first momentum solve.
            initial_pressure = next((item["static_pressure_pa"] for item in case["environment"].get("pressure_outlets", []) if item["fluid_region_id"] == region_id), 101325)
            _write(root, f"0/{region_id}/p_rgh", _foam_file("volScalarField", "p_rgh", f"dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform {initial_pressure:.17g};\n" + _boundary_field(case, region, meshes, "p_rgh"), location=f"0/{region_id}"))


__all__ = ["write_runnable_dictionaries"]
