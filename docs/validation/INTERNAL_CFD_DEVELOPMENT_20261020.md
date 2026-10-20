<!-- SPDX-License-Identifier: Apache-2.0 -->
# Internal CFD/CHT development verification, 20 October 2026

Status: **bounded experimental development verified; not production, arbitrary
enclosure/aerodynamics, two-way FSI or release qualification.** No existing
failed PEEC, PI/SI, platform or release gate was removed or promoted.

## Delivered

1. An owned C++ steady conjugate-energy solver reusing accepted native MAC flow
   faces. Fluid and solid temperatures share one conservative thermal system.
2. SI material/regime admission, strict versioned schemas, identity and actual
   field/flux/residual admission, bounded OS process supervision, worker routes
   and CLI. Incomplete solves expose no accepted fields.
3. Explicit sparse overlap transfer for heat and traction, with action/reaction
   signs, geometry/context binding and adjoint reverse displacement/velocity
   fields. This is transfer infrastructure, not a second participant time solver.
4. Six executed CHT examples and conservative split-patch handoffs, plus a
   staged plan for general meshes, enclosures/exchangers, external aerodynamics,
   turbulence, rotors, broader fluid regimes and mechanical/aeroelastic coupling.

Read the [native method](NATIVE_CHT_METHOD_20261020.md),
[surface method](../COUPLED_SURFACE_EXCHANGE.md), [examples](../../examples/internal_cfd/README.md)
and [delivery stages](../INTERNAL_CFD_AND_FSI_PLAN.md).

## Actual executed checks

| Scope | Outcome | Retained evidence |
| --- | --- | --- |
| MSVC x64 Release old cavity plus new CHT CTests | 2/2 passed, 100.78 s | `build/native-cht-20261020/Testing/Temporary/LastTest.log` |
| Python 3.11.9 CFD/CHT/transfer/process/schema and prior channel/reference regression group | 74 passed, 0 skipped, 10.419 s | `build/native-cht-20261020/final-python-domain.log` |
| Same domain group on Python 3.12 | 74 passed, 0 skipped, 10.899 s | `build/native-cht-20261020/final-python312-domain.log` |
| Actual native examples and three-level heat refinement | 6 runs and 11 checks passed; consumed sources unchanged during and after execution | `build/internal-cfd-examples-20261020-001/report.json` and all requests/results |
| Independent numerical/API recheck after range repair | 10 checks passed; no remaining findings in reviewed scope | `build/native-cht-20261020/independent_review_receipt.json` and reproducible script |
| Architecture and button/control standards | Passed | `npm run check:architecture` |
| Source whitespace, schema catalog and reference inventory | Passed at execution | `git diff --check`, schema tests in group above, reference generator `--check` |

The 74-test command used `.venv-emerge3/Scripts/python.exe -m unittest` with
modules `test_native_cht`, `test_internal_cfd_contracts`,
`test_coupled_surface_exchange`, `test_service_cfd`, `test_native_airflow`,
`test_schema_catalog`, `test_internal_airflow`, `test_laminar_channel_cht` and
`test_cfd_reference_correlation`, all under `tests.python`. Native environment
overrides selected the two newly built executables in
`build/native-cht-20261020/Release`; no stale native binary was silently used.

Actual source-worker processes executed `run_native_cht`,
`run_coupled_surface_exchange` and `cfd_capabilities`. Actual CLI processes
executed both new routes and validated their schema results. An actual native
process cancellation returned no result. These are source-development
process tests, not installed-application or clean-machine qualification.

The independent closed-form conduction heat is 10/105 W for the default
one-metre span. The example differs by 4.696e-12 W, below its predeclared
1e-9 W tolerance. Moving-case successive heat changes are 0.0004399612 W and
0.0002061004 W on 8/16/32 grids. Decreasing changes are not a measured error
bound or complete manufactured Navier-Stokes/energy verification.

## Review feedback incorporated

Independent review reproduced intermediate underflow in the original reverse
map for a 1e-300 m2 patch, 1e300 source intensity and 1e-30 reverse field.
The admitted result now retains the reverse value 1e-30 and zero pairing defect.
Exponent-aware products avoid false intermediate overflow/underflow; a true
nonzero result below representable range fails explicitly. Subnormal geometry
areas fail admission. An exact dyadic fallback preserves representable signed
cancellation when floating-point summation overflows internally. The original
counterexamples, forward/pairing range failures and cancellation rechecks pass.

Native result admission independently recomputes local Fourier/enthalpy energy
balance from the returned field. A corrupted interior temperature cannot reuse
a fabricated zero residual, even when outer/interface fields are unchanged.
Returned MAC face fluxes, cell averages, global mass and both thermal interface
flux/temperature conditions are also checked. No field is normalized or clipped
to manufacture acceptance. Floating evaluation tolerances are not rigorous
interval proofs or continuum error estimators.

## Evidence bindings

SHA-256, not signing or release approval:

| Artifact | Digest |
| --- | --- |
| Native CHT executable | `2f4c9c6727279d944de99890f868330880f0583eee3aa20d318222bc91c1d7d9` |
| Final 74-test log | `a6eaad17a65bd030e65fd8aa705abaac6f836f86c6fc1dca189719a8e412b041` |
| Six-case source/binary-bound report | `043d5ed6b981f906f430c4074088f31c55697cb5801a1d5921f509caaa81f555` |
| Independent review receipt | `03b819825f177903e0140e4ccb10668eeab02f88eefedc7cb8249a5e5ce1988b` |

The native method record separately binds compiled C++ sources, CMake, test
and raw CTest log. The example report binds its consumed source set, exact
material/geometry settings and returned outputs. These deliberately bounded
records are not a coherent full-repository or four-platform release manifest.

## Remaining scope

No arbitrary enclosed CAD flow, 3-D unstructured momentum, buoyancy, thermal
startup, fan, exchanger-specific validation, turbulence, compressibility,
multiphase/cavitation, rotating mesh, external aerodynamics, dynamic structural
feedback or flutter was qualified here. No automatic CAD contact/overlap or
moment-preserving transfer was added. No external CHT correlation, measured
validation or knowledgeable human numerical release review is claimed.
The previous failed full-suite/release record is not relabelled using this
passing domain group. Native CHT is not added to existing shipped installers;
new platform/packaging/UI qualification remains separate. No commit, push,
signing or publication was performed by this increment.
