<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->

# Deployable solver-suite program

Latest airflow work: [startup, non-cuboidal geometry, buoyancy/SST and public
measured-reference status](ENCLOSURE_RUNTIME_INCREMENT_20260907.md). Executable
experimental configurations are distinguished from still-open production gates.

Native geometry generation now executes for typed planar PCB prisms/holes/tubes:
[OCC process, evidence and remaining scope](OCC_CONFORMING_PCB_MESH.md). The
[fan boundary update](OPENFOAM_FAN_BOUNDARIES.md) now executes a real inlet/outlet
CHT fixture through 10 seconds in OpenFOAM 2606 (Ubuntu/WSL), including mesh
checks and field import. [Conservation/refinement and multiboard evidence](FAN_CHT_QUALIFICATION.md)
now includes six executed cases and a separately powered/unpowered two-board
coupling test. General enclosure production approval remains open; local
refinement sensitivity is not automatically proof of an asymptotic order.

Mesh/MoM development: [analysis families and mesh roadmap](ANALYSIS_AND_MESH_ROADMAP.md)
records integrated manual track controls, conforming tetrahedral refinement,
constrained quality optimization and verified RWG basis construction. MoM
field solving and general CAD tetrahedralization are still pending.

Latest enclosure/PCB development increment: see
[implementation and verification scope](ENCLOSURE_PCB_INCREMENT.md). Closed
voxel Stokes flow, entity-bound lumped ports, rotated rectangular pads and
corrected one-watt/radius-aware NF2FF normalization are implemented. General
enclosure thermal airflow and arbitrary-PCB conforming meshing remain pending.

Deployability is a property of a bounded workflow and its evidence, not a
synonym for “the function executes.” Run the authoritative report with:

```powershell
python scripts/run_solver_suite_deployability.py --output build/solver-suite-deployability.json
```

The command returns `2` while any requested product capability is blocked. It
derives promotion only from the reviewed native capability ledger. A request,
UI flag, external solver, local passing test or unauthenticated JSON document
cannot promote a capability.

## Dependency-ordered delivery

1. Qualify PI AC/broadband and the bounded 3-D solid-thermal reference in
   parallel as independent foundations.
2. Complete PI transient and conforming full-solid thermal execution.
3. Qualify general SI extraction and time-domain channel analysis.
4. Add general wave ports, adaptive full-wave sweeps and open-boundary evidence
   for basic RF.
5. Qualify calibrated near/far-field, shielding, LISN and chamber workflows for
   EMI/EMC.
6. Close the conservative electrical-loss to thermal-source loop, including
   temperature-dependent conductors/devices, nonlinear relaxation, transient
   storage and energy conservation.
7. Add CHT/airflow, then reuse the same typed coupling, checkpoint and evidence
   architecture for magnetic-thermal, multiboard and later fluid/mechanical
   couplings.

Every deployable workflow requires native ownership, strict contracts, analytic
verification, convergence/property testing, independent-solver comparison,
measured correlation with uncertainty, Windows/Linux determinism, resource and
cancellation tests, clean packages, auditable private CI and an immutable
release-qualification binding. External engines remain comparison or optional
acceleration paths; they do not become the product owner.

## Current numerical increment

`spike/structured-solid-thermal-request/v1` is an executable, bounded
cell-centred 3-D finite-volume reference. It supports diagonal anisotropic
conductivity, harmonic material interfaces, contact resistance, prescribed
temperature, convection, inward heat flux, surface radiation, implicit-Euler
transients, sparse solves and explicit linear/energy residuals. It is
deliberately recorded as `experimental`: it does not replace the conforming
assembly mesher, airflow/CHT, external correlation or release evidence needed
for full thermal support.

## Post-freeze numerical review and coupling increment

The structured thermal reference now evaluates radiation at a solved surface
temperature, including the half-cell conduction drop. Every transient step
passes residual/energy acceptance. Conservation uses absolute boundary
throughput plus an explicitly reported floating-point allowance. Analytical
radiation tests cover heating/cooling and a zero-K environment; a three-axis
anisotropic manufactured solution demonstrates second-order spatial convergence
over four grids, and an RC decay demonstrates first-order time convergence.
Sparse-direct execution is limited to 16,384 cells and two million cell-steps;
these conservative limits do not provide OS-enforced process memory control.

`structured_electrothermal.py` adds steady DC resistor/MNA to solid-field
coupling. It checks electrical power balance, conservative cell deposition,
positive temperature-dependent resistance and unrelaxed coupling defects.
Failure or cancellation publishes no partial fields. Its analytical quadratic
fixture is verification evidence only. General electrical material fields,
semiconductor models, transient coupling, CAD geometry, distributed execution
and measured correlation remain required for full electrothermal deployment.

## Priority integration — 2026-09-05

The release task lifted the source freeze before this increment. The previously
staged reference is now in `python/spike_core/transient_diode_field.py` and has
permanent tests. `scripts/run_structured_solid_thermal.py` dispatches the new
`spike/transient-diode-field/v1` request contract. The pulsed example is
`examples/thermal/transient_diode_field_request.json`.

This is implicit backward-Euler coupling of prescribed forward-current diode
reference models to the structured thermal field, with transpose temperature
sampling, conservative heat deposition and per-step convergence/energy checks.
It is **not** arbitrary semiconductor/SPICE integration: no junction charge,
breakdown, transistor/switching losses, electrical-state rollback or device
checkpoint is inferred. It remains a verification reference, not production
qualified. Exact recurrence, timestep refinement, independent two-cell matrix,
pulsed storage, finite-output and cancellation checks are permanent regressions.

Thermal qualification validation now rejects negative/nonfinite/non-JSON-numeric
error metrics and requires independent/measured references on the matching gate,
not merely anywhere in the evidence document. This validates metadata, not the
authenticity of referenced measurement files; no capability was promoted.

Next integration priorities remain exact PCB outline/cutout/material lowering and
conforming mesh/port ownership; transactional per-device temperature/power exchange
with the existing owned SPICE engine; actual mass/momentum/energy airflow and
conservative fluid-solid coupling; admitted complex/64-bit PETSc/hypre/MPI builds
with real multi-rank tests; and independent/measured correlation with uncertainty.
None of these larger gates is satisfied by the bounded reference increment.

## Frequency-domain process mapping — 2026-09-06

The public native adapter now accepts `options.native_study` equal to
`{"type":"frequency_domain"}`. Frequencies, coefficients and prepared modal
operators remain in the SHA-bound physics-model artifact; study-level port,
frequency, executable and time-integration overrides reject. Runtime model
validation and capability admission still apply.

The updated adapter was exercised through the real native executable using the
private prepared-modal process examples in place: two-mode/two-frequency success,
tampered model digest, unsupported input, stale operator identity and unsupported
checkpoint cases all passed their expected assertions. Eleven public adapter
tests passed. This closes the envelope mapping gap, not the general full-wave
physics gap. Results remain `verification_only` and public product physics is
not promoted. No airflow, far-field or general PCB mesh implementation is inferred.

## Cross-board field and modal references — 2026-09-07

See [the field/mode increment](CROSSBOARD_FIELD_MODE_INCREMENT_20260907.md)
for the separate explicit-material assembly compiler, actual four-excitation
FDTD examples, full incident-wave matrix normalization, and three-mesh physical
cavity frequency/Q reference. The [NBS measured comparison](NBS_YAGI_COMPARISON.md)
adds actual field-solver discrepancy evidence, with geometry/feed differences
explicitly retained. These bounded results do not enable arbitrary AssemblyIR
field compilation, general physical-mode completeness or production qualification.
