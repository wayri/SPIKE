# Native CFD and SU2 comparison, 2026-10-11

## Executed case and gate

Independently authored square cavity: L=1 m, moving top-wall speed U=1 m/s,
density 1 kg/m3, viscosity 0.01 Pa s, Reynolds number 100. Other walls are
stationary and impermeable. No energy equation or solid regions are present.
SU2 8.5.0 runs natively on Windows; WSL is not required by this adapter.

Before execution, the comparison declared convergence for both solvers,
decreasing cross-solver maximum centerline error with refinement, and finest
maximum differences no greater than 0.03 U. Interior sample positions are
0.05 through 0.95 at 0.05 intervals. The two native grid arrangements are
interpolated to those positions; wall-corner discontinuities are excluded.

| Cells per solver | Max horizontal difference / U | Max vertical difference / U | Native max divergence, dimensionless |
| --- | --- | --- | --- |
| 16 x 16 | 0.0462153 | 0.0531449 | 3.39290e-12 |
| 32 x 32 | 0.0289158 | 0.0293990 | 2.64588e-12 |
| 64 x 64 | 0.0160007 | 0.0156980 | 1.49547e-12 |

All six runs converged. SU2 pressure and both velocity log10 residuals were
below -9. Native steady velocity rates were below 1e-7 for ten consecutive
steps. The declared comparison gate passed. SU2 centerlines continue changing
with refinement, so this gate is not a continuum error estimate.

## Evidence and reproduction

The local HTML report described in the
[release evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md) includes
unit-labeled velocity plots and interpretation. The
full comparison JSON. Neither generated artifact is shipped; use the reproduction
commands below and retain a reviewed sanitized result before citing it as public evidence.
retains executable/input hashes, convergence and per-grid profiles. Each grid
also has native and SU2 result JSON, and managed SU2 mesh/config/solution logs.
The separate local runtime has download provenance under
`artifacts/su2-runtime/provenance.json`; it is not a release payload.

```powershell
python scripts/build_native_airflow.py --generator "Visual Studio 18 2026"
python scripts/benchmark_su2_airflow.py --cells 16 32 64 --output "$env:TEMP/spike-cfd-su2-comparison"
python scripts/render_cfd_benchmark.py "$env:TEMP/spike-cfd-su2-comparison/comparison.json"
python scripts/run_cfd.py --capabilities
python scripts/run_cfd.py --engine native --request tests/fixtures/cfd/native-cavity.json --output "$env:TEMP/spike-native-cavity.json"
```

## Checks actually performed

- Native CTest passed, including independently derived cosine pressure oracle,
  second-order operator refinement, incompatible flux rejection, rest state,
  failed-run admission and cavity refinement (82.88 s).
- Six native Python admission/scaling/failure tests passed.
- Six SU2 mesh/CSV/identity/convergence/cancellation/input-mutation tests passed.
- Three CFD service request-boundary tests passed.
- Native CLI execution completed and saved a converged result.
- Rust heavy-worker routing test, TypeScript compiler and architecture guard passed.
- Documentation link check passed after integration; plots were visually inspected.

The full repository test suite and native GUI CFD workflows were not run for
this isolated foundation. No release or installation was performed.

## Scope remaining

Three-dimensional retained STEP/PCB air domains, temperature transport, natural
convection, fan pressure curves, turbulence, radiation and solid-fluid CHT remain
outside these two adapters. Assembly extension must preserve material/contact
identity, local interface energy balance, mesh convergence and shared thermal
benchmarks before admitting those modes. Numerical human review is required
before release. Cross-code agreement alone does not establish either solver's
absolute accuracy or hardware correlation.
