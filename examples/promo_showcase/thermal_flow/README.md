# Original thermal and flow showcase

SPDX-License-Identifier: Apache-2.0

Copyright 2026 Yawar B (wayri) and SPIKE contributors. All authored meshes, original hollow-case STEP, scripts, requests and generated result datasets in this subpack are first-party original SPIKE material under the included Apache-2.0 license. They contain no third-party board CAD. The authoring runtime uses separately installed Gmsh/OpenCASCADE; their binaries and source are not redistributed here. Native cavity and channel CHT use existing first-party SPIKE numerical owners.

## Native-ready projects

`case-contact.spike` and `poor-contact.spike` each reopen through the native package API with state **current** and saved transient results. Open in SPIKE desktop, choose Multi-board → Thermal/Assembly volume field study. The saved setup uses SPIKE reference tetrahedral solver and Transient solid thermal. Select **Run transient thermal** to execute anew. The thermal volume viewer supports saved-frame playback and native GIF/WebM export. Alternatively, in an already saved project use **Open volume study** to import the corresponding `.fieldstudy.json`.

These are original illustrative homogeneous PCBs inside an actual closed hollow case. Board20×20×1.6mm; outer case28×28×12mm, cavity24×24×8mm. The board sits on the case base; there is a2mm air gap from the board edge to the cavity walls. Empty cavity has no fluid mesh or heat-transfer model. Only the declared board-bottom/case-base interface transfers heat between bodies; cavity interior surfaces are adiabatic. Case external surfaces use prescribed h10W/(m²K), ambient300K. This is solid thermal with a convection boundary, not CFD/CHT.

PCB k0.5W/(mK), density1800kg/m³, cp1000J/(kgK); case k150W/(mK), density2700kg/m³, cp900J/(kgK). These are illustrative constant inputs, not a characterized real PCB or alloy. Uniform PCB power0.2W; both bodies initially300K. Time120s, backward-Euler step2s, output every5s. Good contact h500W/(m²K) equals5K/W over400mm²; poor contact h5 equals500K/W. Board peak303.413K versus318.876K, showing a bounded case heat-sink/contact comparison.

Reopen/digest checks, physical frame count, unchanged solver heat/energy acceptance, contact comparison and independent tetra-volume/capacity-energy arithmetic passed. Independently integrated input24J minus convection agrees with stored energy within2.1e−9J in both runs. No temporal/spatial convergence study or hardware correlation was run for this illustrative geometry. Imported structured-mesh hashes remain caller declarations; OCC STEP and mesh share authored dimensions but no automatic CAD-to-mesh source-authentication claim is made.

## Flow status

`native-cavity.request.json` / `.result.json`: freshly executed native16×16 Re100 cavity, converged. Native UI reproduction: command palette **Native CFD cavity benchmark**, Domain → Conditions Re100 → Grid & runtime16×16 → Check / retry runtime → Review & run → Run native CFD. The panel has no JSON request importer. **Show fields in main viewport** presents actual returned fields. This is fixed isothermal2D cavity, not this enclosure and not a physical transient animation.

`channel-cht.request.json` / `.result.json`: freshly executed existing bounded conjugate laminar-channel owner; completed with energy check. **Request-only**, not a native project/UI import. Its existing research API is `solve_laminar_channel_cht`; do not substitute the UI's internal-airflow screening or native cavity for this exact CHT model. Arbitrary enclosure CFD/CHT and real-board operating assumptions are outside this subpack.

## Reproduce from repository root

```
.venv/Scripts/python.exe examples/promo_showcase/thermal_flow/build_thermal_flow.py
.venv/Scripts/python.exe examples/promo_showcase/thermal_flow/verify_outputs.py
.venv/Scripts/python.exe examples/promo_showcase/thermal_flow/run_flow.py
```

Thermal authoring requires the admitted local Windows OCC/Gmsh runtime used by `tests/python/test_assembly_joint_thermal_mesh.py`. Analysis reuses existing SPIKE owners, no new constitutive law or solver implementation. All results remain experimental and unqualified. API package reopen was validated; this subtask did not operate the desktop UI or record videos.
