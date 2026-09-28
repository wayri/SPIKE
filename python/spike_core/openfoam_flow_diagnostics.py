# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Trusted fixed function objects for constant-density CHT energy observations.

These declarations collect storage and signed advective transport, NOT a
complete energy qualification. Generic inlet/outlet conduction must additionally
be obtained from the solver-consistent face-normal thermal flux. wallHeatFlux
is restricted to wall patches and cannot substitute for that measurement.

OpenCFD references (API contracts, not implementation copied):
https://api.openfoam.com/2606/classFoam_1_1functionObjects_1_1fieldValues_1_1surfaceFieldValue.html
https://api.openfoam.com/2506/classFoam_1_1functionObjects_1_1fieldValues_1_1volFieldValue.html
https://api.openfoam.com/2212/fluid_2solveFluid_8H.html
"""
from collections.abc import Mapping
import re


def _word(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value):
        raise ValueError("Diagnostic region and patch names must be bounded literal words")
    return value


def render_flow_energy_objects(region_kinds, open_patches, *, orthogonal_constant_k=False):
    """Return function entries (without functions braces), plus observation metadata.

    Fixed field names are solver-owned h, K, p and mass flux phi. Region density
    multiplies volume integrals of h/K externally. Do not use absWeightedSum:
    inflow must retain its negative sign. Functions execute and write every step.
    Hook into controlDict before input hashing, after wallHeatFlux declarations.
    """
    if type(orthogonal_constant_k) is not bool:
        raise ValueError("orthogonal_constant_k requires an explicit Boolean")
    if not isinstance(region_kinds, Mapping) or not 1 <= len(region_kinds) <= 64:
        raise ValueError("Expected one to 64 region identities")
    if not isinstance(open_patches, Mapping) or set(open_patches) - set(region_kinds):
        raise ValueError("Open patches must belong to declared regions")
    chunks, observations = [], []
    def add(name, region, body, *, write=True):
        chunks.append(f"    {name}\n    {{\n        {body}\n"
                      "        libs (fieldFunctionObjects);\n"
                      f"        region {region};\n"
                      "        executeControl timeStep;\n        executeInterval 1;\n"
                      + ("        writeControl timeStep;\n        writeInterval 1;\n" if write else "        writeControl none;\n") +
                      "        writePrecision 17;\n        writeToFile true;\n"
                      "        log false;\n    }")
    for region, kind in sorted(region_kinds.items()):
        _word(region)
        if kind not in ("solid", "fluid"):
            raise ValueError("Only solid and fluid regions supported")
        patches = open_patches.get(region, [])
        if not isinstance(patches, list) or len(patches) > 64:
            raise ValueError("Expected bounded patch list")
        for patch in patches:
            _word(patch)
        if len(set(patches)) != len(patches) or (patches and kind != "fluid"):
            raise ValueError("Open fluid patches must be unique")
        fields = "h K p" if kind == "fluid" else "h"
        name = f"spikeEnergyVolume_{region}"
        add(name, region, "type volFieldValue;\n        operation volIntegrate;\n"
            f"        fields ({fields});\n        writeFields false;")
        observations.append({"name": name, "kind": "volume_integrals", "fields": fields.split()})
        if orthogonal_constant_k and patches:
            add(f"spikeEnergyGradient_{region}", region,
                "type grad;\n        field T;\n        result spikeEnergyGradT;", write=False)
        for patch in sorted(patches):
            name = f"spikeEnergyAdvection_{region}_{patch}"
            add(name, region, "type surfaceFieldValue;\n        regionType patch;\n"
                f"        name {patch};\n        operation weightedSum;\n"
                "        weightField phi;\n        fields (h K);\n        writeFields false;")
            observations.append({"name": name, "kind": "signed_advective_power", "fields": ["h", "K"]})
            name = f"spikeMassFlux_{region}_{patch}"
            add(name, region, "type surfaceFieldValue;\n        regionType patch;\n"
                f"        name {patch};\n        operation sum;\n"
                "        fields (phi);\n        writeFields false;")
            observations.append({"name": name, "kind": "signed_mass_flow", "fields": ["phi"]})
            if orthogonal_constant_k:
                name = f"spikeEnergyConduction_{region}_{patch}"
                add(name, region, "type surfaceFieldValue;\n        regionType patch;\n"
                    f"        name {patch};\n        operation areaNormalIntegrate;\n"
                    "        fields (spikeEnergyGradT);\n        writeFields false;")
                observations.append({"name": name, "kind": "normal_temperature_gradient_integral",
                    "fields": ["spikeEnergyGradT"], "power_multiplier": "minus_region_conductivity_w_mk",
                    "scalar_component": 0, "scope": "constant_k_orthogonal_mesh_only"})
    return {"dictionary_entries": "\n".join(chunks), "observations": observations,
            "energy_qualification_complete": False,
            "required_additional_observations": ["solver-consistent conduction on every external patch",
                "initial storage and every time-step record", "actual source power",
                "confirmation whether thermo dpdt is enabled", "interface-flux cancellation"]}
