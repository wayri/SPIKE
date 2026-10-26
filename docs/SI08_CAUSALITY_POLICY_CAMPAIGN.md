<!-- SPDX-License-Identifier: Apache-2.0 -->

# SI08-I02 causality, DC and grid policy campaign

This finite campaign qualifies the existing bounded preparation policy, not
causality of arbitrary supplied measurements. `sparameter_sampling` retains
exact source samples, explicit source/supplied real DC, Cartesian interpolation,
no extrapolation and unchanged original identity. `sparameter_rational` can
construct a stable proper model at explicitly supplied positive real poles;
that is a property of its realization rather than proof about its input.
No numerical implementation or public schema is changed here.

## Finite targets and reference checks

The [independent derivation and original witnesses](validation/SI08_I02_CAUSALITY_ORACLE_20261025.md)
specify Fourier signs, delayed/advanced and resonant/time-reversed references,
finite-grid ambiguity, interpolation refinement and frozen tolerances. Exact
continuous-time support is known because these fixtures are analytically
constructed. A finite sweep alone does not recover that support. Tests retain
causal and deliberately noncausal sources without inventing a source label from
a sample count, smooth curve, small fit residual or stable fitted poles.

`examples/si08_causality_policy/run_campaign.py` composes unchanged resampling
and an optional explicitly controlled real-pole fit. Its neutral report keeps
`source_causality=unknown_from_finite_samples`, independently reports the
constructed model's causality (or `not_constructed`), and preserves both source
snapshots. There is no inferred DC, automatic pole selection, passivity repair,
calibration, out-of-band qualification or production claim. Bad grids, controls,
fit admission and DC states retain the existing owners' failure behavior.

The source-bound campaign executes the independent witnesses, three reporting
checks and all original sampling/contract/rational regressions. Invoke
`scripts/verify_si08_interoperability.py --point I02 --output FRESH.json --log FRESH.log`.
The validator checks current before/after source bindings, exact test inventory,
all outcomes, the retained log and false physical/native/family/release flags.
Separate adversarial checks reject point substitution, missing tests, stale
logs/sources and overclaims.

I02 does not fulfill I05 automatic complex-pole passive broadband fitting,
I06 loaded model validation, I07 complete product workflows or external E01/E02.
Those remain finite independent checklist points. Source causality evidence
beyond this policy needs applicable additional measurements or prior physical
assumptions; no finite-band diagnostic is silently promoted to physical proof.
