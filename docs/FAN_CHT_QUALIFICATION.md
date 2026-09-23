<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Fan CHT and multiboard numerical evidence

## Implemented and executed

The optional OpenCFD OpenFOAM 2606 Ubuntu/WSL worker runs one or two separate
heated board regions coupled to one shared air region. Both boards retain their
own source zones, material identity, fields and reciprocal mapped interfaces.
The generated example uses two parallel 10 mm square, 1.6 mm thick boards
bounding an 8.4 mm air duct; it is not arbitrary enclosure CAD compilation.
The existing multi-region request also accepts independently specified board
loads; the example generator supports `board_count=1` or `2`.

All six cases in `build/fan-qualified-study-20260907/report.json` completed
10 seconds of physical time, checkMesh, and field import with unchanged
execution source hashes. Cases use 2/4/8 divisions per coordinate and timesteps
0.004/0.002/0.001 s, plus a two-board case at 4 divisions and 0.001 s.
The two-board run imports 192 cells: 64 per board and 64 air cells.

## Conservation measurement

Fixed, non-coded function objects record every timestep. Constant-density
sensible-enthalpy accounting volume-integrates solid `rho*h` and fluid
`rho*(h+K)-p` (energy densities) when dpdt is enabled, and sums signed boundary
`phi*(h+K)` and outward conductive flux. Here `K=|U|^2/2` is specific kinetic
energy in J/kg and `phi` is face mass flow in kg/s. Pressure work is not added
again to enthalpy advection.
The equation and thermodynamic switch follow the documented OpenCFD
[energy equation](https://api.openfoam.com/2512/heatTransfer_2chtMultiRegionFoam_2fluid_2EEqn_8H_source.html)
and [basicThermo dpdt setting](https://api.openfoam.com/2306/basicThermo_8C_source.html).

The validator verifies input digests, literal thermodynamic/laminar settings,
aligned timestep histories, explicit dpdt accounting and unchanged output
hashes. Study qualification additionally regenerates the declared fixture to
verify all input identities and checks actual mesh orthogonality. The gradient
normal integral is appropriate only for this verified orthogonal constant-k
case, not a general nonorthogonal-face heat-flux qualification.

Euler right-endpoint integration matches the executed temporal discretization.
The first saved timestep is the baseline: intervals start at dt, not zero.
Startup energy before that baseline remains unqualified. The preset local
energy threshold is 0.001, checked both cumulatively and per timestep; this is
not the native solver's Milestone 0 exit gate.

| Case | Cumulative relative energy defect |
| --- | ---: |
| 2 divisions | 9.98e-9 |
| 4 divisions | 7.06e-8 |
| 8 divisions | 3.16e-7 |
| dt = 0.004 s | 1.53e-10 |
| dt = 0.002 s | 1.48e-7 |
| Two powered boards | 7.16e-8 |

All six local energy checks passed. Evidence with hashed diagnostic histories:
`build/fan-qualified-study-20260907/energy.json`.

## Refinement

Temperature rise above 298.15 K, rather than absolute Kelvin, normalizes the
comparison. Preset local change thresholds are 2% mesh and 0.5% timestep.
The initial finest-level changes are 0.365844% mesh and 0.000346797% timestep.
Both satisfy the local change criterion. **Neither initial sequence establishes
an asymptotic order:** the mesh peak is nonmonotonic and the timestep differences
do not fit a positive leading error order. The evaluator reports this explicitly
and does not manufacture Richardson estimates.

Initial evidence: `build/fan-qualified-study-20260907/refinement.json`.
The completed extension at `build/fan-refinement-extension-retry-20260907`
adds 16 divisions (8,192 total cells) and timesteps 0.016/0.008 s. Its
`refinement.json` compares 4/8/16 divisions and 0.016/0.008/0.004 s:

| Observable: peak temperature rise | Mesh | Timestep |
| --- | ---: | ---: |
| Finest relative change | 0.133331% | 0.000189654% |
| Three-point leading-error fit | 1.4543 | 2.7318 |
| Estimated fine observable error | 0.002842 K | 0.000001241 K |

Both sequences are monotonic and satisfy the same preset local thresholds.
These are **observable-specific three-point fits**, not proof of asymptotic
accuracy or the formal order of the discretization (Euler remains first order).
The original nonmonotonic/indeterminate sequences remain in the evidence.
All three extension energy audits also passed: defects 2.80e-10 (dt 0.016),
1.43e-9 (dt 0.008), and 1.98e-8 (16 divisions). All ten full-length cases,
including the independent cross-heating run, completed with stable execution
source hashes. The largest cumulative energy defect among them was 3.16e-7.

## Cross-board heat transfer

`build/multiboard-cross-heating-20260907/report.json` records a second actual
three-region solve: lower board 0.1 W, upper board 0 W. At 10 s, lower-board
mean temperature is 301.78924385 K and upper-board mean is 298.15016379 K.
The unpowered-board warming check passed, with energy defect 7.07e-8 relative.
The warming is small (0.164 mK); this is a numerical coupling smoke test, not
measured hardware correlation or a practically significant heating claim.

## Reproduce

Use new, empty output directories:

```powershell
python scripts/run_fan_cht_study.py --output build/new-fan-study --wsl-native-scratch
python scripts/evaluate_fan_energy_study.py build/new-fan-study --output build/new-fan-study/energy.json
python scripts/evaluate_fan_cht_study.py build/new-fan-study --output build/new-fan-study/refinement.json
python scripts/run_multiboard_cross_heating.py --output build/new-cross-heating
python scripts/run_fan_refinement_extension.py --output build/new-extension
python scripts/evaluate_fan_energy_study.py build/new-extension --output build/new-extension/energy.json
python scripts/evaluate_fan_cht_study.py build/new-fan-study --extension build/new-extension --output build/new-extension/refinement.json
```

Linux scratch is opt-in and retained with its exact path in each result.
Commands remain fixed argv and bounded. Input identities are checked before
staging and after copying results back. Gradient fields stay in memory; only
their integrated observations are written each timestep. Earlier superseded
runs are preserved: the original drive-backed study was stopped after its solve,
and an initial scratch copy timed out while copying unnecessary per-step
gradient fields. Neither is included in accepted study evidence.
An extension preparation that failed runtime discovery before solver launch is
also preserved separately. The retry used an explicitly probed 2606 runtime.
The 61 focused unit/regression tests and architecture checks passed. A read-only
independent math audit checked the original eight energy records, units,
refinement percentages and cross-board temperature rise.

## Remaining production work

The subsequent [enclosure runtime increment](ENCLOSURE_RUNTIME_INCREMENT_20260907.md)
adds actual time-zero auditing, an explicit no-dpdt constant-density policy,
non-cuboidal execution, bounded density-law buoyancy and forced-flow SST.
Its passed and failed cases have separate scopes; they do not supersede these
duct-only refinement results or establish arbitrary-enclosure qualification.

These are executed numerical examples, not general enclosure production
approval. Arbitrary enclosure/PCB CAD construction, nonorthogonal conservative
face-flux diagnostics, startup balance, fan operating curves, buoyancy/turbulence,
obstruction/recirculation validation, broader multiboard layouts, independent
solver and measured correlation, and clean-machine qualification remain open.
No general-production capability flag was enabled by these local tests.
