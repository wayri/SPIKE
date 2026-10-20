<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Refined obstacle-inertial enclosure verification, 20 October 2026

Status: experimental mathematical verification, not production or measured
qualification. The [workflow](../ENCLOSURE_CHT_REFINED.md),
[independent momentum derivation](ENCLOSURE_RECTILINEAR_MOMENTUM_20261020.md),
[retained sensible-energy derivation](ENCLOSURE_CHT_METHOD_20261020.md) and
[ADR 0121](../adr/0121-refined-obstacle-inertial-enclosure-cht.md) define scope.
All implementation, polynomial test fields and benchmark inputs are independently
authored. No external solver implementation or dataset was adapted.

## Executed matrix

The later [current-source replay](ENCLOSURE_FLOW_BENCHMARKS_20261020.md) adds
the isolated stress/SA/rotation checks and reruns the affected legacy partition
after the private optional momentum extension. The following earlier runs
remain historical execution evidence, not a claim that their source identity
includes the later extension.

- Python 3.11.9: **151 scoped CFD/CHT tests passed**, no skips, warnings as errors;
  log `build/enclosure3d-refined-domain-20261020.log`.
- Python 3.12.9: **24 new momentum/obstacle/v2 tests passed**, no skips, warnings
  as errors; log `build/enclosure3d-refined-py312-20261020.log`.
- Two additional actual generic-worker/catalog and oversized v2 wire tests
  passed on Python 3.11; log `build/enclosure3d-refined-worker-20261020.log`.
  The scoped 151 run preceded these two new tests; it is not reported as a
  single 153-test run.
- Actual v2 CLI and headless worker completed refined obstacle cases. Strict
  schemas validate execution results, reject unknown fields and forbid partial
  fields on unsuccessful results. Existing v1 behavior/gates remain unchanged.

The 151 run includes existing native execution tests using trusted host
overrides to the previously built CHT/airflow executables and workspace-local
TEMP/TMP. No native numerical source changed in this increment; no new native
backend or new native build is claimed. No UI, installed package, Linux/MPI,
whole-project suite or public-release qualification is claimed.

## Source-bound coupled benchmark

Command actually executed with warnings as errors:

```powershell
.venv-emerge3\Scripts\python.exe -Werror scripts\benchmark_enclosure_cht_v2.py `
  --output build\enclosure-cht-v2-benchmark-20261020-postrotation
```

Receipt: `build/enclosure-cht-v2-benchmark-20261020-postrotation/receipt.json`.
SHA-256: `1fab26b2fcd099e7201fe45acb6c5b709df55aed1f7af6a87da5de02e3461ba7`.
Four exact request/result pairs and nine matching source/schema hashes are
retained. Dependency binding includes reused v1 admission and Stokes helpers;
the benchmark was genuinely rerun after those bindings and the private optional
Coriolis-block extension were added. Its default nonrotating path passed again.
The prior `final-root` receipt (`d5ad1257b0f0dbf1728106bdfc20ef6c4cf0793ff337ddf85ef8c347e61898f2`)
is historical pre-extension evidence, not the current source identity.
Earlier agent receipts remain historical, not hash-patched into current evidence.

| Observable | Actual result |
| --- | ---: |
| Refined obstacle Reynolds upper bound | 2.026900184 |
| Nonlinear iterations | 5 |
| Coarse / refined momentum unknowns | 108 / 1104 |
| Refined independently recomputed divergence | 2.9680e-18 /s |
| Corresponding divergence budget | 1.5e-12 /s |
| Refined relative heat imbalance | 1.3878e-16 |
| Two-component hydrostatic pressure-step error | 5.5511e-17 Pa |
| Uniform transient temperature error | 0 K |
| Integrated startup energy defect | 1.4658e-16 J |

The refined result is demonstrably a different actual momentum solve, not
prolongation. The reference fluid is deliberately synthetic, density 200000
kg/m3, to exercise inertia at small velocities and negligible unmodeled viscous
heating. It is not air, water, a real material recommendation or physical
validation. Drive work is approximately 3.74e-9 W; heater input is 0.8 W.
Temperature uses the explicitly modeled sensible source, not an invented
conversion of drive work into heat.

## Spatial evidence and accuracy limits

The kernel ledger records ten executed uniform, nonuniform and disconnected
slab manufactured runs. Full-box finest velocity errors are 1.1433% and 1.2779%
on uniform and selected-cut nonuniform grids, respectively. Uniform full-box
order >1.8 and finest error <0.02 remain enforced. Nonuniform observed orders
are 1.77808 and 1.90151; no universal second-order step/obstacle claim follows.

An independent actual re-entrant obstacle test excludes the corner
`x>=0.5 and y>=0.5` from the unit cube. Its continuous polynomial
streamfunction vanishes with first derivatives on every wall. Polynomial
differentiation supplies forcing including nonzero inertia, not a source fitted
to the discrete assembler. No SymPy or other new dependency is required.

| Cells per axis | Weighted relative face-velocity L2 error | Reynolds bound |
| --- | ---: | ---: |
| 8 | 0.2678224814 | 4.73756 |
| 12 | 0.1638231166 | 3.96606 |
| 16 | 0.1037588033 | 4.25880 |

Observed orders 1.21228 and 1.58758 pass the separately predeclared 0.8 gate;
finest error passes 0.12. These do **not** establish 2% arbitrary-obstacle
accuracy: the finest case still has approximately 10.4% error. The early coarse
rho=1 four-to-eight-grid order of about 0.49 remains recorded as failed
pre-asymptotic evidence, not reclassified as a pass. Inertial/viscous forcing
norm ratio is about 3.6-3.8%, and all three accepted grids take six iterations.

## Independent review findings repaired

1. At spacing 1e-100 m, a dimensional residual floor plus underflowed dot
   products accepted a half-relaxed velocity with 50% unresolved error. Stable
   max-scaled norms now use the actual RHS scale with an explicit exact-zero
   branch. Checked elementwise power products reject unrepresentable arithmetic;
   BLAS reductions alone did not expose underflow. Both relaxation choices now
   reject the 1e-100/1e-60 controls without fields. At safe spacing 1e-20 m the
   direct and 34-iteration damped solutions agree; true damped residual is
   about 5.82e-11. The method ledger states the strict representability envelope.
2. Finite extreme face values could overflow an independent divergence audit
   to NaN, bypassing its comparison. Final JSON publication would already reject
   NaN, but the audit now rejects derived overflow/invalid arithmetic before
   thermal execution. Its regression is permanent.
3. New v2 also rejects source/storage multiplication underflow before heat
   assembly. Nonzero tiny heat is not silently turned into zero. No old
   equation, gate, raw result or retained failed run was changed to manufacture
   success.

Independent agent review supports these checks; it is not the required
knowledgeable human numerical review before release.

## Still open

Confined local momentum AMR, curved/nonorthogonal geometry, transient momentum,
inlets/outlets/far fields, variable-stress/closure coupling into CHT,
wall treatment, rotating/sliding/ALE blade geometry, rotor loads and matched
measurements remain unfinished. The [turbulence/rotor record](TURBULENCE_ROTOR_REQUIREMENTS_20261020.md)
identifies exact primary specifications, required operators and future benchmark
candidates, **not executed turbulence or propeller validation**. Runtime flags
remain false. Existing failed PEEC and release gates are not promoted.

Separate in-process [flow research APIs](../ENCLOSURE_FLOW_RESEARCH.md) now
verify prescribed symmetric stress, fixed-velocity SA-noft2 transport and
whole-frame Coriolis momentum. They do not widen this v2 workflow or establish
coupled engineering turbulence/rotating propellers.
