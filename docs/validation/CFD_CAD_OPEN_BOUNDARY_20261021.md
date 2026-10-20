<!-- SPDX-License-Identifier: Apache-2.0 -->
# CAD / open-boundary tetrahedral increment — 21 October 2026

## Scope and acceptance

This increment adds independently authored tetrahedral topology/geometry
admission, a source-preserving existing-OCC bridge, CR/P0 creeping Stokes flow
and RT0/P0 steady conductive/advective energy. It does **not** complete general
engineering CAD CFD, physical inertial open boundaries, engineering turbulence
or turbulent CHT. No public capability, worker dispatch or release gate is
promoted. See [workflow](../CFD_TETRA_WORKFLOW.md) and the separate
[mesh](CFD_TETRA_MESH_20261021.md), [flow](CFD_TETRA_STOKES_20261021.md) and
[energy](CFD_TETRA_ENERGY_20261021.md) derivations, exact references and bounds.

`scripts/generate_cfd_step_fixtures.py` creates original box, sheared-prism and
cylinder STEP fixtures using the previously admitted optional Gmsh/OCC runtime.
This is **not a new internal standalone CAD mesher**. Its pinned local-only
installation/redistribution/transitive-DLL limits remain unchanged. The fixture
native process actually uses the existing OS memory/time containment; the
in-process SciPy solvers have cooperative deadlines, not interruptible native
factorizations or OS-enforced memory limits.

`scripts/benchmark_cad_cfd_open_flow.py` runs real STEP meshing, explicit fixture
surface assignments, SI geometry admission, flow and same-topology energy.
The fixed quadratic family has mesh targets .5/.35/.25/.18 mm, finest relative
velocity L2 <=.05 and endpoint effective-h order >=.8. Pressure errors are
reported, not claimed to pass an unprovided universal pressure-accuracy gate.
The affine cylinder patch has relative velocity error <=1e-8 and pressure RMS
normalized by .05 Pa <=1e-7. Each CAD volume must match its analytic source
volume to relative1e-10. Flat-facet mesh-vs-curved-CAD volume discrepancy is
reported separately, not hidden as exact curved geometry.

The energy coupling check requires maximum absolute error <=1e-8 K for uniform
350 K with requested 300 K reference, using actual solved mass flux, rho=1,
cp=1000 and k=.6. It additionally compares signed patch advective heat against
the source flow certificate times rho*cp*350 to relative1e-10. Uniform temperature
alone cannot establish transfer sign/magnitude; adversarial tests deliberately
reverse or scale enthalpy and require failure. This is constant-state and
conservative-transfer verification, **not heated/turbulent CHT validation**.

## Defects discovered by actual execution

1. Real curved CAD revealed that `occ.affineTransform` even for identity
   converts an analytic cylinder to B-splines and changes the reported volume
   from pi/2 to1.58432935269405 mm3: relative error0.00861539186736. Native
   translate/rotate preserve analytic Cylinder/Plane/Plane surfaces and pi/2.
   The retained STEP importer now reuses the existing rigid-placement helper;
   it changes no transform admission or analytical tolerances. The exact
   controlled probe and raw, hash-bound output are retained in
   `build/cfd-rigid-occ-probe-20261021/`.
2. An affine harmonic flow exposed a free-equation residual normalization
   defect: a7.0141e-22 N defect divided by already-cancelled stiffness terms
   falsely gave0.862. Separating original free/fixed operator terms gives
  1.4066e-15 without changing the1e-10 gate. The derivation and regression are
   in the Stokes record. A distinct zero-work energy-normalization corner is
   still rejected; it was not waived.
3. Finest direct Stokes factorizations exceeded unchanged resource limits.
   Bounded iterative solving and cached exact geometric predicates replace
   those costly operations, rather than raising caps or shrinking the declared
   refinement sequence. Failed attempts remain in the flow/mesh records.
4. The first same-mesh constant-temperature energy run passed coarse cases
   but failed the finest box's fixed1e-9 local energy gate. Its exact request
   and rejected no-field result remain under
   `build/cad-cfd-open-flow-final-20261021/box-0.18/`. Final accepted evidence
   must demonstrate a numerical repair, not an increased tolerance or hash
   refresh. Source-changing diagnostic runs are not final qualification.

The energy repair uses an internal area-weighted boundary-temperature lift,
without changing the caller's requested reference. The original absolute-T
equation still includes the actual accepted mass defect multiplied by cp*T;
it is not discarded. Both retained finest requests pass when re-executed,
and a new independently constructed SI-scale case reproduces the old failure
with the lift disabled. A nonzero accepted mass-defect oracle distinguishes
350 K conservation from incorrect 300 K/50 K accounting. Details and measured
values remain in the energy record.

An [independent numerical review](CFD_TETRA_LINEAR_REVIEW_20261021.md) checks
the closed-component volume-mean pressure multiplier against a different
reference-pressure algebra, SPD block preconditioning and residual/scale/
resource negative controls. No pressure penalty or local mass-row deletion is
introduced. This review is not a substitute for the finest-grid runtime and
accuracy tests, a rigorous condition bound or human numerical release review.

## Executed checks and retained evidence

Both Python3.11 and3.12 ran the22 mesh/energy tests successfully before the
actual-CAD feedback repair. Two additional cross-solver/adversarial quadrature
tests passed on3.11. A57-test related regression run passed in147.900 s,
covering existing OCC meshing/runtime/fragment coverage, tetra optimization/
refinement, enclosure CHT v2, symmetric stress and independent/research mean-SA
equations. These checks do not qualify engineering turbulence.

## Fresh post-repair native benchmark

Executed with warnings treated as errors:

```text
.venv-emerge3/Scripts/python.exe -Werror scripts/benchmark_cad_cfd_open_flow.py --fixtures build/cfd-step-fixtures-final-20261021 --output build/cad-cfd-open-flow-qualified-increment-20261021
```

Exit0; all9 cases passed, `sources_unchanged=true`, with108 hashed output
artifacts. The retained report is
`build/cad-cfd-open-flow-qualified-increment-20261021/report.json`.
It is an accepted **bounded increment**, not general CAD/engineering CFD
qualification. The earlier failed runs are retained separately.

| Real STEP fixture | Mesh targets (mm) | Tetrahedra | Relative velocity L2 errors | Endpoint effective-h order |
|---|---|---|---|---:|
| Box | .5/.35/.25/.18 | 110/216/423/1198 | .097692/.047598/.036991/.019630 | 2.0161 |
| Sheared prism | .5/.35/.25/.18 | 139/212/466/1276 | .079764/.049382/.038250/.018346 | 1.9887 |
| Cylinder affine patch | .25 | 652 | 6.7855e-16 | Not a refinement study |

Across9 cases, maximum uniform-temperature error was0 K and maximum signed
source-flow/thermal-enthalpy transfer error was1.4521e-16. Each flow/energy
solver independently passed its unchanged residual, local conservation,
energy, conditioning and resource gates before returning fields. Cylinder
CAD volume error was1.4136e-16, while its separate flat-facet tetra volume
error was2.8591%; this approximation is reported and not relabeled exact.
The cylinder normalized pressure RMS was8.3082e-15. Quadratic-family pressure
errors remain explicitly reported, without an unsupported accuracy claim.

The9 saved flow certificates have maximum scaled linear residual2.8529e-15,
free-equation residual3.2838e-15, local scaled mass defect7.4222e-16 and
broken-gradient energy defect8.0423e-16. A separate post-run audit recomputed
all15 selected source hashes and108 artifact hashes successfully; it did not
rewrite the report. The separate zero-work translation limitation remains
fail-closed, rather than being masked by these nonzero-gradient examples.

## Post-repair integration checks

The complete40-test increment suite passed with `-Werror` on Python3.11.9
(50.502 s) and Python3.12.9 (51.194 s). Modules:

```text
tests.python.test_cfd_tetra_mesh
tests.python.test_cfd_tetra_stokes
tests.python.test_cfd_tetra_energy
tests.python.test_cad_cfd_benchmark
tests.python.test_assembly_thermal_cad
```

Both were run sequentially with task-scoped `OPENBLAS_NUM_THREADS=1` and
`OMP_NUM_THREADS=1`; default Stokes request limits stayed30 s. These controls
do not change a tolerance or enlarge a runtime cap. The separate owner11-test
Stokes run passed in38.919 s, including both unchanged3072-tetra refinement
cases. Earlier resource failures and concurrent-workload timeouts are retained
in the Stokes record, not substituted with a60-second accuracy claim.

After those40-test checks, the related57-test suite was rerun against the
final implementation on Python3.11 with `-Werror` and the same single-thread
environment: all57 passed in193.787 s. It covers OCC meshing/runtime/fragment
coverage, tetra optimization/refinement, mean-SA research/independent checks,
enclosure CHT v2 and symmetric stress. The geometry owner's additional14
existing native assembly/encapsulation tests also passed after redirecting
only the runner's temporary directory into the writable build workspace;
the original default-temporary-directory publication errors remain documented.
Architecture and targeted whitespace checks passed. The recorded-reference
inventory was regenerated and its check passed with674 distinct references.
The inventory records links, not proof of adoption or qualification.

Full project tests, Linux, independent
matched engineering-flow/measured correlation and release qualification have
not been established by these focused checks. Knowledgeable human numerical
review remains required. General multi-material CAD/air-domain extraction,
layered/local flow meshing, inertial physical open boundaries, qualified
turbulence and turbulent CHT remain incomplete; no gate has been removed.
