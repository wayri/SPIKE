# Temperature feedback into dielectric conductivity

PI02-S04 extends the verified one-way [dielectric-to-thermal workflow](PDN_DIELECTRIC_THERMAL.md)
with a bounded steady fixed-point iteration. Electrical conductivity changes
with temperature according to explicit supplied laws. Permittivity, loss tangent
and thermal conductivity remain fixed. No material law is inferred from its name.

Call `run_pdn_dielectric_feedback(request)` in
`python/spike_core/pdn_dielectric_feedback.py`, or the worker method with exactly
`{request: ...}`. The request contract is
`spike/pdn-dielectric-feedback-request/v1`, containing `base_request` (the existing
one-way request), `conductivity_laws` and `iteration`.

Each original used electrical material needs exactly one law:

```json
{
  "material_id": "bulk",
  "reference_temperature_k": 300,
  "temperature_coefficient_per_k": 0.02,
  "temperature_range_k": [290, 350]
}
```

Conductivity is `sigma_ref × (1 + alpha × (Tcell − Tref))`, in S/m. The reference
conductivity comes from the original electrical material. Each cell uses the
mean of its four nodal temperatures; all its nodal temperatures must remain in
the supplied validity range. The multiplier must be positive throughout that
range. No clipping or extrapolation is allowed. This is a supplied linear law,
not a validated model for a particular material.

Iteration controls are `initial_temperature_k`, `max_iterations` (at most 100),
`relaxation` in (0,1], `temperature_tolerance_k` and
`power_relative_tolerance`. Every iteration executes the actual AC-to-thermal
workflow. Conductivity is constant within each P1 cell and updated between
iterations. Per-cell material IDs are generated explicitly in both copied
meshes; coordinates, cell/node ordering and source owners retain their identity.
The result records original/generated material mappings and digests. Original
requests and material definitions remain unchanged.

## Convergence and independent reference

Convergence uses the raw difference between the thermal target and the
temperature used to evaluate conductivity, plus relative change in total
dissipated power. Relaxation applies only to the next trial state. A small
damped update cannot masquerade as convergence. Results retain both the
operating temperature used for electrical properties and the final returned
thermal field, so their residual is visible. Exhaustion, invalid ranges,
numerical failure or cancellation return no successful partial study.

An independent discrete reference uses a one-cell-wide cube with all electrical
nodes on fixed-voltage faces. Its electric P1 field is fixed, while thermal
nodes on one face are free. For temperature rise theta from Tref, the exact
coupled discrete system is `(K − H) theta = f0`, where
`He=volume × sigma_ref × |E|² × alpha / 16 × ones(4,4)` and
`f0e=volume × sigma_ref × |E|² / 4 × ones(4)` (with constant dielectric loss
added when present). This full coupled linear solve independently checks the
iterative workflow, including positive and negative feedback. It is a discrete
P1 reference, not a continuum accuracy claim.

The method, code and synthetic fixtures are independently authored SPIKE work.
Zero-coefficient compatibility, raw residuals under relaxation, source/material
ownership, law coverage/ranges, resource limits and cancellation are checked.
Each subsolve retains electrical/volume power agreement and thermal heat balance.

## Validity limits

Results remain experimental, `production_qualified=false`, with coupling mode
`two_way_conductivity_temperature`. This extends the original PI/SI program's
multiphysics foundation; full stack parity remains open. Steady fixed-point
convergence does not establish transient stability or rule out physical thermal
runaway. No feedback is applied to permittivity, loss tangent, thermal
conductivity, geometry or mechanical state. More general material tables,
cross-mesh transfer, fluid/structural coupling and measured validation require
separate stages. The thermal subsolve retains its existing cancellation limits.
Knowledgeable human numerical review remains required before release.

## Reproduce the computed comparison

```powershell
.venv/Scripts/python.exe examples/pdn_dielectric_thermal/run_feedback.py --plot
```

The [original synthetic example](../examples/pdn_dielectric_thermal/run_feedback.py)
executes both fixed-conductivity and feedback studies and saves request, result
and comparison/convergence plots under `build/pdn-dielectric-feedback-example`.
Plotting uses the installed development Matplotlib package. For its supplied
law, the actual feedback solve converges in 17 iterations: dissipated power
increases from 50.0314 W to 54.1677 W and computed peak temperature from
306.254 K to 306.684 K. Both raw residuals meet their independent criteria.
These are synthetic supplied material parameters, not measurements.

Admission bounds include 8 MiB input, 16 MiB output and one billion estimated
repeated-work units, accounting for bounded electrical/thermal work and geometry
audits. Temperature tolerance is restricted to 1e-10..1 K, and relative power
tolerance to 1e-12..0.01. No timing or general scalability claim follows from
these admission bounds.

## Stage verification

PI02-S04 is **Done** for its bounded acceptance. Nine zero-skip checks passed
in the [source-bound execution](validation/parity/PI02-S04.json). Positive and
negative feedback agree with the independently assembled discrete system to
less than 3e-13 K in the tested cube; a relaxed stronger case agrees within
5e-10 K. Tests reject false closure from tiny relaxed updates, invalid laws,
range violations, exhausted iteration budgets and cancelled work. Original
input/material ownership and reported property-evaluation temperatures are checked.
The actual worker passes request/result schemas and raw residual criteria.
Six affected prior stages were re-executed and their receipts refreshed.
Full release and knowledgeable numerical review remain separate gates.

Combined PI/SI, thermal, worker/schema and evidence regressions passed 131
tests with zero skips in 14.514 s (`build/parity-pi02s04-focused.log`).
Architecture, ten documentation checks and the 61-family backlog check passed.
