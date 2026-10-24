<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# AC dielectric loss to heat to elastic response — 23 October 2026

Status: experimental, in-process, one-way coupling. No worker/UI route or
production capability is enabled. [ADR0128](../adr/0128-same-mesh-ac-thermal-elastic-chain.md)
records the ownership and boundary. This increment connects existing numerical
owners; it adds no new constitutive law or numerical implementation language.

## Input, execution and provenance

Call `run_pdn_dielectric_thermomechanical(request)` from
`python/spike_core/pdn_dielectric_thermomechanical.py`. Exact request keys:

- `contract`: `spike/pdn-dielectric-thermomechanical-request/v1`.
- `electrothermal_request`: the existing [AC/heat request](../PDN_DIELECTRIC_THERMAL.md).
- `structural_request`: the existing [tetrahedral structural request](../COUPLED_MECHANICS_MAGNETICS_DEVICES_PLAN.md#current-bounded-mechanical-interface).

All three child meshes must match by indexed geometry, units, material IDs,
ownership and canonical bytes. Electrical/structural supplied context digests
must agree; this does not independently authenticate a CAD revision. Caller
structural temperatures must be null. Existing heat sources must remain absent
to prevent double counting. Properties and constraints are supplied, not inferred.

The structural owner preflights at null eigenstrain, then AC/thermal are actually
executed. Actual solved Kelvin temperatures feed a fresh structural solve.
No external result substitution or second thermal solve occurs. The original
requests remain unchanged. Subsolve errors/cancellation/resource failures never
publish partial coupled success. Thermal callback cancellation remains between
subsolves; process containment is still required for hard interruption.

Output retains complete electrical/thermal evidence, structural fields and
reactions, original/generated structural digests and transferred-temperature
identity. Parent/structural hashes use sorted compact unescaped-Unicode UTF-8
JSON. The legacy electrothermal owner uses ASCII-escaped Unicode. Both profiles
are named and checked; child hashes are not rewritten or treated as identical
for Unicode inputs. Nonfinite JSON and aggregate payloads beyond 8/16 MiB
request/result limits fail, alongside unchanged child solver bounds.

## Governing mathematics and independently authored oracles

For one coherent RMS tone, `q=Re(E^H D E)` in W/m3 with
`D=sigma*I+omega*tan(delta)*epsilon`. Combine fields before evaluating loss;
RMS phasors have no extra factor1/2. The existing field owner checks volume loss
against real terminal power. The heat owner solves `-div(k grad T)=q` and retains
source/boundary heat balance. Structural eigenstrain is
`alpha*(mean_cell(T)-Tref)*I`, with `sigma=C:(epsilon-epsilon_thermal)` and
elastic energy `integral(.5*sigma:epsilon_elastic)dV`. Elastic energy in J is
not equated to electrical power in W or half the external work under thermal
eigenstrain. This is steady, not transient thermodynamics or feedback.

For the synthetic one-metre slab with uniform field10V/m at1kHz,
sigma0.5S/m, epsilon1e-6F/m and loss tangent0.05,
`q=(0.5+2*pi*1000*1e-6*0.05)*100=50.0314159265 W/m3`.
With k1W/(m K), both ends300K and insulated sides,
`T(x)=300+q*x*(1-x)/2`. For full nodal clamping with E2GPa,
nu0.25 and alpha1e-5/K, stress is hydrostatic
`-E*alpha*deltaT/(1-2nu)*I`; von Mises stress is zero despite nonzero
compressive normal stress. Tests independently recover this sign, tensor and
stored energy. A separate zero-loss/uniform350K case verifies free expansion.

Reviewed 23 October2026: [Staelin, MIT6.013 notes, copyright2011](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/d3be4ea78b036a6362230fb41780cf54_MIT6_013S09_notes.pdf),
section2.7.1–2.7.2, displayed pp56–59, equations2.7.6 and2.7.13–2.7.27:
power density and harmonic averaging. Peak-amplitude formulas are converted to
RMS explicitly above. [Bower, Applied Mechanics of Solids, section3.2.2 and
strain-energy subsection](https://solidmechanics.org/Text/Chapter3_2/Chapter3_2.php):
reviewed thermal-strain isotropic tensor law and elastic strain energy, including
engineering-shear convention. No external implementation/example/data copied.
These are established governing references, not a novelty or measured-validation
claim. Earlier provenance gaps and knowledgeable human release review remain.

## Executed verification

On the local Windows Python environment, BLAS/OpenMP threads1: **59 tests passed**
across the new coupling and six affected AC/thermal/feedback/structural modules.
Ten new test methods cover slab field/heat/stress, free expansion, unknown fields,
mesh/context and Unicode identities, no double heating, forged child records,
negative/nonfinite/type-invalid temperature, rigid preflight, cancellation and
bounded payloads. Three-level temperature-centroid refinement requires slope
at least1.7; acceptance is not based solely on global conservation.

The separate broader CFD/mesh/energy/CAD-transfer replay passed39 tests after
an initial default-timeout failure and unchanged isolated rerun. See the
[CFD repair record](CFD_TETRA_ZERO_WORK_20261023.md). Combined scoped coverage
is98 passing tests; this is not the complete repository or release suite.

The runnable example reuses the independently authored existing slab geometry:

```powershell
.venv/Scripts/python.exe examples/pdn_dielectric_thermomechanical/run_slab.py --output build/my-ac-heat-stress
```

Output must be fresh. Requests, actual results, input/artifact/source SHA-256
and measured refinement metrics are retained. No plot or model result is mocked.
Both the initial run and final selected-source-bound replay produced the
following. The final local report is
`build/dielectric-thermomechanical-final-20261023/report.json`, SHA-256
`e3e79062076711c3b551531d574df27e1e5225a6fa8809ea4b228ded20fb481b`.
It fingerprints nine selected source files and the retained request/result
artifacts, not a complete transitive environment/SBOM or signed release.

| Tetrahedra | Power W | Peak temperature K | Temperature-centroid L2 K | Elastic energy J |
| ---: | ---: | ---: | ---: | ---: |
| 6 | 50.031416 | 300 | 5.263464 | 0 |
| 48 | 50.031416 | 306.253927 | 1.315866 | 6.844530 |
| 384 | 50.031416 | 306.253927 | 0.328966 | 10.939026 |

Temperature slopes were2.000000 and2.000000. The coarsest mesh has no interior
temperature nodes: its apparent300K maximum is **not** a resolved physical peak.
Mechanical stress is qualified against the transferred discrete temperatures,
not claimed fully converged against a continuous mechanical solution. The
elastic-energy values visibly still change with refinement; no mechanical
continuum/board accuracy gate is marked complete.

After the local AC per-basis repair, the chain was re-executed against current
source in `build/dielectric-thermomechanical-ac-repair-20261023/report.json`,
SHA-256 `b685510609edf9c9e947230115a534adb1d78f9a74037cd71f8ffa5bf7282697`.
It reproduced the table to displayed precision and slopes
2.0000000000000995 and 1.9999999999976177. The earlier report above is retained
historically, not asserted to bind the newly repaired AC source.

## Remaining scope

This is finite-domain electroquasistatic dielectric loss, not copper skin/proximity
loss, arbitrary SI channels or general PCB extraction. No nonlinear temperature
feedback, deformation-remeshing feedback, transient storage, airflow, contact,
plasticity, fatigue, dynamics, material catalog or measured-board validation.
No release, MPI or cross-platform qualification is inferred from these runs.
