# SPIKE and WayriCAD QuickTherm package thermal comparison

## Working-tree inspection, 2026-10-10

This comparison applies to the inspected local source, not an installed or
published capability claim. QuickTherm's relevant files are in the sibling
`kiWay/quick_therm_plugin` directory and include concurrent untracked work.

| Capability | SPIKE | QuickTherm inspected source |
| --- | --- | --- |
| Board temperature field | Layered board/grid model | Layer-resolved approximate board model |
| Package junction estimate | Requires an explicit model and heat mapping | Board site temperature plus declared power times RθJB, or unknown |
| Package CAD volume | Separate retained STEP promotion and Gmsh OCC workflow | Not present in inspected CalculiX bridge |
| External thermal mesh | Retained solid/assembly workflow | Board triangles extruded as DC3D6 layer wedges |
| Package interfaces | Reviewed materials, transforms and contact setup required | Bridge rejects separate contacts; prescribed bottom temperature |
| Rendering | Display models alone do not establish thermal coverage | A board overlay does not establish a solved package volume |

QuickTherm `thermal_calculix.py` rejects vias/drilled pads, mount contacts,
bottom-side sources and unsupported boundary conditions. Its board-only
external case uses an isothermal bottom and otherwise adiabatic exterior.
These restrictions concern this bridge; they do not erase cooling features
in its separate reduced board solver.

SPIKE's `assembly_thermal_components.py` requires a retained, digest-bound STEP
reference, occurrence identity, reviewed rigid mounting transform and explicit
material assignment. Promotion establishes geometry eligibility, not a solved
or converged device junction temperature. See
[retained component solids](THERMAL_COMPONENT_SOLIDS.md).

## Evidence and limits

The focused QuickTherm CalculiX, multilayer and geometry suites ran using
KiCad 10 Python: **30 tests passed, no skips**. They cover deck/FRD parsing,
fixtures and saved-board extraction; they do not establish an executed ccx
reference solve or real package-solid accuracy. Its README also records the
absence of real external-engine validation.

Existing SPIKE component promotion and assembly meshing tests cover retained
CAD admission and geometry; they do not qualify the user's displayed board
as a package-solid thermal study. No same-case cross-tool comparison or
hardware accuracy claim is made here.

QuickTherm is GPLv3 and SPIKE is Apache-2.0. Share independent study fixtures,
units and result contracts; do not transplant implementation code.

## Shared benchmark to implement and execute

Start with independently constructed rectangular closed STEP solids, rather
than an arbitrary visual package model:

1. A 10 × 10 × 2 mm homogeneous slab, conductivity 10 W/(m K), uniform
   top heat flux totaling 1 W, bottom fixed at 25 °C, other faces adiabatic.
   Analytical top temperature is **27 °C**: ΔT = P L/(k A) = 2 K.
2. Two such slabs in series with a reviewed 1 K/W total contact resistance.
   Expected top temperature is **30 °C**: 2 + 1 + 2 K above the fixed base.
3. A package/board assembly with distinct materials and a documented contact
   area, then transient power steps with density and heat capacity. Compare
   against the same retained CalculiX geometry, sources and boundaries.

For each tool retain geometry/source hashes, occurrence IDs, SI units,
material provenance, contact resistance convention (total K/W versus area
specific m² K/W), mesh statistics, boundary definitions and raw temperatures.
Require three mesh levels, energy balance, fixed physical probe locations and
explicit tolerances chosen before comparison. For the analytical slabs use
≤1% temperature-rise error and ≤0.5% power-balance error; contact jumps must
converge to P R. These are proposed acceptance gates, not achieved results.

QuickTherm must first implement package-solid admission/contact solving before
it can participate in the second and third volume benchmarks. Its reduced
Rθ estimates should be labeled and compared separately. Missing geometry,
materials, contacts or failed solve must leave a clear blocked/unknown state;
never infer package thermal coverage from visible 3D models.
