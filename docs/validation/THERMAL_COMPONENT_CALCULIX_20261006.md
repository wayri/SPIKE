# Component meshing and CalculiX electrothermal verification — 2026-10-06

## Implemented scope

Reviewed retained component STEP promotion, joint conformal multiboard/part
meshing, retained-resistance interface discovery, explicit thermal-only circuit
packages and occurrence-aware mesh/temperature visualization are implemented.
See [desktop steps and requirements](../THERMAL_COMPONENT_SOLIDS.md).

## Actual engine evidence

The original full-chain fixture executes the pinned Gmsh 4.15.2 process on two
board prisms and a promoted closed STEP package, compiles and solves the native
MNA harness/resistor circuit, deposits the existing device's loss in package
tetrahedra, and executes CalculiX 2.23 at each temperature-feedback iteration.
The resistance coefficient is 0.004/K. It checks KVL and loss identities to
1e-12, conservative heat mapping, separate occurrence node ownership,
unrelaxed temperature/power convergence gates of 0.002 K and 1e-6, and saved
JSON offline admission. The volume-mean analytical slab temperature rise is
checked within 2% discretization tolerance plus 0.002 K printed-output allowance.
Test: `tests/python/test_calculix_meshed_electrothermal.py`.

The independent contact oracle uses two 2×2×1 mm solids, conductivity 2 W/(m K),
a reviewed 50 K/W interface, and 300/400 K end faces. Each solid contributes
125 K/W; exact heat flow is 1/3 W and interface temperatures are 341.6666667 K
and 358.3333333 K. Generated interfaces and autolinking reproduce these values
with internal temperature tolerance 1e-6 K and CalculiX tolerance 0.002 K.

Independent review found that tolerant CAD fragmentation could close a positive
1e-8 mm gap. The corrected gate checks shared triangles against original finite
convex planar source faces before accepting the mesh interface. Actual Gmsh
checks reject gaps of 1e-8, 1e-10 and 1e-12 mm, reject overlap and an out-of-patch
coplanar triangle, and retain exact/rotated touching interfaces. No nearest-face
welding is used. Representation roundoff and unsupported interface shapes are
documented in the workflow guide.

## Interface and integration checks

- Full Python discovery: 2,811 tests run, 20 skipped, no failures, 541.973 seconds.
  Log: `.local/thermal-parts-complete-python-tests.log`. Real engine tests below
  cover the interpreter-specific cases skipped by the project Python runtime.
- Real Python 3.11 engine suite: 22 tests passed in 37.484 seconds, including
  actual Gmsh/CalculiX contact and complete electrothermal fixtures.
  Log: `.local/thermal-parts-real-engines.log`.

- UI harnesses cover contact discovery/selected application, explicit resistance,
  STEP/material/mounting review, stale jobs and unmount, circuit rebinding,
  thermal-only declarations, solver selection and saved result admission.
- Volume viewer checks cover global color scale, Kelvin/Celsius, occurrence
  extrema, bounded interior edges/samples, memoized geometry and stale results.
- TypeScript, parser, architecture, button-standard and production UI build pass.
- Native Rust checks: 38 passed, 1 ignored; new heavy methods and project-path
  classification are covered.
- Documentation UTF-8, local links and anchors pass.

An early full discovery run exposed a test-file name collision that removed an
existing imported fixture. The original tracked thermal-part tests were restored
and the new circuit package tests moved to
`test_multiboard_volume_thermal_only_parts.py`; all 20 affected original/new/study
regressions pass. The complete discovery rerun passes after that repair.

## Limits

One closed solid per retained STEP model; explicit material and mounting datum;
64 joint source solids and existing output and process budgets. Shared curved,
concave or holed CAD faces are blocked by source-interface admission. Sub-roundoff
separations cannot be distinguished; large coordinate scales that exceed the
roundoff cap are rejected. Boards use reviewed effective layer materials.

These synthetic references do not qualify hardware, arbitrary CAD, airflow,
thermal transients or full-wave electrothermal behavior. Thermal setup supports
the existing explicit exterior convection/radiation and solid conduction paths;
it does not infer cooling coefficients or package junction resistance.

Native visual acceptance at wide/narrow window sizes remains outstanding. The
open native window contained unrelated unsaved work and was preserved. No
installer or release was produced; numerical release still requires knowledgeable
human review.
