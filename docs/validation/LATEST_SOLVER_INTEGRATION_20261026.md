<!-- SPDX-License-Identifier: Apache-2.0 -->
# Latest solver integration audit, 26 October 2026

This is a source and retained-evidence audit for the 0.4.2 integration freeze.
It changes no governing equations, numerical thresholds, native binaries or
production qualification. The live C: checkout, the D: beta snapshot and an
installed executable are distinct artifacts. Checks below do not establish
that an eventual 0.4.2 installer contains the audited source.

## Current source capabilities and evidence

- The shared viewport player admits saved layered-board thermal, selected
  spatial PI transient and CFD field-volume frames. It preserves physical
  timestamps and uses a separate presentation clock. Direction markers follow
  computed saved curves at display speed; they are not physical particle
  trajectories. See [playback](UNIFIED_VIEWPORT_PLAYBACK_20261026.md).
- The declared-cuboid adapter constructs a partitioned air complement and paired
  solid/fluid interfaces for the existing OpenFOAM multi-region CHT route.
  Native streamLine export retains returned positions, U/T samples and actual
  output times. Strict per-region checkMesh admission and malformed-field
  rejection remain active. See [geometry review](RECTILINEAR_CHT_GEOMETRY_20261026.md).
- Later source adds volume-only Gmsh Netgen optimization with an unchanged
  surface-node/connectivity guard, then conforming tetrahedron-to-four-hex
  subdivision before ordinary polyMesh export. Original source vertices,
  interfaces, region/source identities, mm-to-m conversion and prescribed watts
  remain explicit. Final cell/vertex budgets and cancellation apply to the
  expanded mesh. See [independent derivation and evidence](ASSEMBLY_AIRFLOW_SUBDIVISION_20261026.md).
- The unsnapped five-region polygon-prism example passes all five strict native
  mesh gates after optimization/subdivision. The retained invariant receipt
  reports 2,032 identical boundary/interface triangles, relative region-volume
  changes <=4.22e-15, and 6,160 tets becoming 24,640 hex cells. Component heights
  remain declared proxies. This is not retained package STEP geometry.
- The subsequent polygon-prism product solve did **not** complete:
  `artifacts/unified-transient-20261026/exact-cad-review/product-cht-summary.json`
  reports the 180-second execution timeout, no execution records and no fields.
  The earlier larger-time-step attempt failed after excessive Courant numbers.
  The translated alternative installed U41 STEP mesh remains rejected by native
  determinant/interpolation-weight gates; rotated STEP fragmentation also has
  an observed native crash. No true-STEP field is available.

Previously retained cuboid CFD fields remain a separate successful short
startup example: 0.02 s, five saved frames, 16 native tracks per frame, five
obstacle-region and two baseline-region mesh gates. No sampled track point
enters a declared component proxy. Different baseline/obstacle meshes confound
quantitative attribution of the observed deflection. The separate PI example
retains 12 frames over 0--10 microseconds for one selected connected +3.3VMCU
track component; backward Euler heavily damps unresolved fast dynamics. The
layered thermal example retains seven frames over 0--600 s and 3,465 board
cells per frame, with a 1.35 W illustrative input and maximum reported balance
error 4.82e-13 W. These are approximate/experimental examples, not board sign-off.

## Source versus frozen artifacts

Read-only frozen-code inspection used the build's Python 3.12.9 interpreter,
`scripts/verify_packaged_source_modules.py`, and both
`--require-em-cosimulation --require-si-ibis-spatial` flags. Code comparison
normalizes filenames only. No packaged application was executed by this check.

| Artifact and baseline | Result |
| --- | --- |
| C: `build/si-ibis-spatial-worker-r1-20261025/resources/spike-worker/spike-worker.exe` versus current C: source | Failed: 555 modules checked; changed package version, service_cfd, openfoam, openfoam_multiregion_execution, assembly_airflow and assembly_airflow_mesh. |
| D: beta `build/unified-transient-worker-20261026/resources/spike-worker/spike-worker.exe` versus D: beta source | Passed: 557 modules checked, no changed/missing modules or missing required SI/EM owners. |
| The same D: worker versus current C: source | Failed: 557 modules checked; changed package version, assembly_airflow and assembly_airflow_mesh. |

The old C: worker's PYZ also lacks the new rectilinear-assembly and native
streamline-export modules. The guard iterates packaged modules; a passing
comparison alone does not detect an additional unbundled current-source module.
Explicit inclusion of the new subdivision owner is therefore required.

The D: backend stage receipt is dated 01:48 on 26 October; frontend final-r4
receipt is dated 01:45. At audit time all 23 frontend/workflow entries in
`sync_frontend_snapshot.py` match C: byte-for-byte, including App.tsx and the
shared-player integration. The frontend receipt records TypeScript/Vite and
transient UI success. The D: unified worker's runtime report was generated at
2026-10-25T20:23:20Z, after that staging in local time, and passes eight runtime
checks against its retained D: baseline. It does not cover the later C: edits.

The exact outstanding C:-to-D: freeze differences are:

- Changed: `python/spike_core/solvers/thermal_fluid/flow/assembly_airflow.py`,
  `assembly_airflow_mesh.py`, `tests/python/test_assembly_airflow_conservation.py`
  and `tests/python/test_assembly_airflow.py`.
- Absent in D: `python/spike_core/solvers/thermal_fluid/flow/assembly_airflow_subdivision.py`,
  `tests/python/test_assembly_airflow_subdivision.py`, this audit,
  `docs/validation/ASSEMBLY_AIRFLOW_SUBDIVISION_20261026.md` and
  `docs/validation/UNIFIED_VIEWPORT_PLAYBACK_20261026.md`.
- Version metadata differs intentionally while the owner coordinates the
  0.4.2 freeze. This audit did not copy, reset or overwrite either tree.

## Executed bounded checks

On current C: source, 32 existing backend checks passed using Python 3.12.9,
`-B`, and the existing D: beta `build/unified-test-temp` directory:

| Existing test scope | Passed |
| --- | ---: |
| test_openfoam_rectilinear_assembly | 4 |
| test_openfoam_streamline_export | 3 |
| test_service_cfd | 4 |
| test_openfoam_multiregion_execution | 10 |
| test_assembly_airflow_conservation | 5 |
| test_assembly_airflow_subdivision | 4 |
| AssemblyAirflowTest seed orientation and nonboundary-plane rejection | 2 |

The first batch's two seed selectors used a plural class name and produced
loader errors without executing those two checks. The 30 other checks passed;
the corrected two selectors then passed separately. No test failure is hidden
by the aggregate count. `npm.cmd run test:transient-ui` also passed all five
scripts against current source, with TEMP/TMP on D:. No heavy native solver,
full build, full-suite rerun or new numerical implementation was performed.

## Full-suite result and open gates

The retained C: `artifacts/unified-python-tests-unsandboxed.log` has a final
result, superseding the earlier playback record's pending-outcome statement:
**5,728 tests, 36,826.251 s, 2 failures, 5 errors, 87 skips** (lines 5877--5879).
The file was created at 01:18:22 and last written at 11:32:48 on 26 October.
It is not a clean frozen-input acceptance run; source advanced during that
interval, and the later subdivision tests do not occur in its test inventory.

- Three parity-backlog errors report `Stale native evidence validator`.
- The RLGC line-junction example exceeds its 60-second subprocess timeout.
- The RLGC loaded-cascade CLI times out; its exception contains a negative
  remaining-time value after the long interrupted run. The cause is unresolved.
- The affine/sheared tetra-Stokes manufactured-solution case returns blocked
  on its runtime budget. A retained focused rerun also failed in 32.610 s.
- Python debug nonfinite publication is rejected in child stderr, but the
  session remains running instead of reaching the required failed state.

The seven failed/error checks require diagnosis and a complete stable-input
run before claiming full Python acceptance. Current focused geometry/playback
success does not waive them. A new worker must include the latest eight backend
owners below, pass source/schema coherence and mandatory runtime/benchmark
probes, then be verified inside the actual installer. Installed-window playback,
clean-machine/offline lifecycle, Linux qualification where required, mesh/time
convergence, complete transient energy audit, measured correlation and
knowledgeable human numerical release review remain separate open gates.
Existing IBIS/SI refinement and device/protocol qualification limits also remain
as recorded in SOLVER_STATUS.md; UI visibility does not promote them.

## Audited backend source identity

SHA-256 snapshot taken during this audit. Prefixes below are repository-relative;
all paths are under `python/spike_core/`.

| Owner | SHA-256 |
| --- | --- |
| service_cfd.py | `19e6c92f55e7879286b362b9612764f863347ea635ed1cd2fcb8b4863aada6b0` |
| solvers/external_engines/openfoam/openfoam.py | `adf2f5bf8545e5758f6a50704cdd91908a73ddffa62647d00abb27afc5906f37` |
| solvers/external_engines/openfoam/openfoam_multiregion_execution.py | `d24a4bc39f415f96be9464dfb38ab6587963975d2e1bc38d97169fc78da46687` |
| solvers/external_engines/openfoam/openfoam_rectilinear_assembly.py | `5693338f66d48c35bb302a0d75866be5cc6d2a118010dc2c186db0f7b929c05f` |
| solvers/external_engines/openfoam/openfoam_streamline_export.py | `6d8328b6900e758309151e799ad0079188ac5ca5730b507565cced032bb25b96` |
| solvers/thermal_fluid/flow/assembly_airflow.py | `a1295017db43cb714367668d9994f3a1e3e5016a6fc2d5d406c2797545bc3d78` |
| solvers/thermal_fluid/flow/assembly_airflow_mesh.py | `1b309b221d5a3083771e9a4d47a2fe175fb64c133f90a498ca99a0dc1f417fad` |
| solvers/thermal_fluid/flow/assembly_airflow_subdivision.py | `b01b046d4b3c9355668af22000420703a9ddebd087898b579297878251dcdbd1` |

Full-suite log SHA-256:
`d6371fe8bca5294b463c97d38867ce89f9a81b08750dc42a30a644dd5f63862c`.
Later source changes require their own updated identity and checks.
