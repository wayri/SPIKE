<!-- SPDX-License-Identifier: Apache-2.0 -->
# Solution-specific thermal accuracy checks

The worker method `validate_assembly_thermal_time_refinement` runs the internal
retained solid transient solver at dt, dt/2 and dt/4. Supply `request`, `problem`,
`transient_settings` from a retained assembly study and explicit `tolerances`:

```json
{"absolute_k": 0.1, "relative_rise": 0.01}
```

This is also available as MCP `spike_validate_thermal_time_refinement`.
It uses the same worker contracts as desktop studies, including multiboard and
reviewed STEP solids. It does not launch another executable or write a project.
Three solves can cost substantially more than one; existing limits apply to
each solve. A worker cancellation terminates the operation; Python callers can
also provide `cancel_check`.

The returned `fine_result` is a normal, digest-bound completed result with its
own finer `transient_settings`. Save it with those settings, not the original
coarse settings. `evidence` binds the original inputs and all three completed
result digests. Evidence remains separate from the solver result and never
changes its experimental status or `temporal_convergence_verified` field.

## Acceptance and recovery

The maximum medium-to-fine difference across every retained node and time is
compared with `absolute_k + relative_rise * max(abs(T_fine - T_initial))`.
All three runs must satisfy their existing integrated energy checks. A small
energy residual alone says nothing about discretization error.

- `within_requested_change`: independent refinements satisfy the authored
  change threshold. This is not a global error bound.
- `refinement_required`: reduce dt and repeat; investigate load events and
  nonlinear response if differences do not decrease.
- `event_grid_limited`: output/source events prevented independent refinement.
  Choose smaller nominal steps. Identical event-clipped grids cannot pass.

An empirical L2 order is reported only for uniform halved grids with resolved,
same-direction changes and decreasing differences. Exactly solved uniform
heating, noise-dominated differences and irregular event-clipped grids produce
no order estimate. Three points do not prove asymptotic convergence.

Mesh refinement and independent solver comparisons remain separate requirements.
No spatial interpolation, unmeasured contact resistance, missing package
structure, fluid model or hardware accuracy is inferred by this check.
See [research and environment roadmap](THERMAL_RESEARCH_ROADMAP.md) and
[CalculiX comparisons](validation/ASSEMBLY_THERMAL_TRANSIENT_20261008.md).

## Independent implementation and oracle

This is independently authored comparison arithmetic, not a copied external
method implementation. It compares the infinity norm of history differences,
RMS differences, and the L2 ratio on uniform refinement. The regression fixture
has a single free tetrahedral temperature with exact semidiscrete decay
`T = 300 + 10 exp(-t)` and exact backward-Euler discrete solution
`T_n = 300 + 10 (1 + dt)^(-n)`. Tests also cover event-limited false passes,
exact insulated heating, invalid tolerances and cancellation. Units are Kelvin
for temperatures/differences, seconds for time, joules for energy.

Implementation: `python/spike_core/thermal_accuracy.py`; regression:
`tests/python/test_thermal_accuracy.py`.
