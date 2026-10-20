<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S02 verification: distortionless lossy line transient

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](RELEASE_040_LOCAL_EVIDENCE.md).

Verified 18 October 2026. **Done for this bounded stage; experimental,
production-unqualified.** SI02 and full PI/SI parity remain open.
The [method ledger](../DISTORTIONLESS_LINE_TRANSIENT.md) retains reviewed primary
lossy telegrapher/Heaviside equations, independently derived attenuated waves,
units, admission limits and coupling ownership. Primary reference: Staelin,
*Electromagnetics and Applications*, chapter 8, sections 8.3.1 and equations
8.3.1-8.3.12 ([MIT OCW](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf)).
Instantaneous loss has no phasor time-average factor of one half.

## Executed evidence

[Canonical source-bound receipt](parity/SI02-S02.json): **9 tests, zero skips**,
six numerical and three actual worker/schema/example checks. Its
actual execution log (unbundled local record: `parity/SI02-S02-distortionless-line-reverified.log`)
retains the executed names. Reproduce into fresh output paths:

```powershell
.venv/Scripts/python.exe scripts/parity_pisi_gate.py --stage SI02-S02 --output build/distortionless-check.json --log build/distortionless-check.log
```

- Matched finite ramps and independently summed geometric echoes check delayed
  attenuation, both-end excitation, ideal-source ends and signed terminal KVL.
- Zero loss matches all parent point fields exactly; added loss fields are zero.
- Independent smooth-wave derivatives check both lossy telegrapher equations.
  Conductor R'I² and dielectric G'V² are checked separately, with total local
  loss equal to 2*kappa*u. Production admission requires relative residual at
  most 1e-10, or exact zero for the zero-scale identity; raw residual is retained.
- Independent space/time Gaussian quadrature checks a finite triangular pulse:
  generator work equals source-resistor heat plus remaining line storage,
  right-end outflow and distributed dissipation. Network injection excludes
  source-resistor heat. A separate characteristic-path integral checks heat.
  These are test oracles, not a production continuous-energy API.
- Time/length scaling, units and shared-sample refinement are checked; malformed,
  nonfinite, precision-lost and resource-excessive requests reject. Work and
  full nested output preflight precede wave evaluation; cancellation is checked.
- Strict registered schemas, original source/digest identity, actual worker
  execution and the executable original 5-m line example are checked.

Preset V/I tolerance is 2e-10 SI absolute plus 1e-9 relative; density tolerance
is 1e-14 J/m plus 1e-9 relative; integrated energy tolerance is 1e-20 J plus
1e-9 relative. The retained probe `build/probe_distortionless_line.py` produces
`build/si02-s02-reference-errors.json`: maximum geometric voltage error
2.220446049250313e-16 V, current error 1.734723475976807e-18 A, and local loss
identity residual 1.0842021724855044e-19 W/m. Network injection was
1.3333333333333339e-11 J. Generator and network energy-balance discrepancies
were 1.9387045606711586e-26 J and 1.7771458472818954e-26 J. Distributed heat was
5.225959040745193e-12 J, differing from the independent characteristic integral
by 3.2311742677852644e-27 J. These are ideal-model numerical errors, not measured
physical uncertainty.

All **23 earlier PI/SI numerical stages** were actually rerun after shared
worker/runner changes. Canonical receipts point to
`*-distortionless-line-reverified.log`; prior receipts are archived as
`*-pre-distortionless-line.json`. No hash-only refresh substituted for execution.
Broader PI/SI, structural/thermal, network, schema and evidence regressions
passed **333 tests**, zero skips/failures/errors (`build/si02-s02-focused.log`).
Architecture passed (`build/si02-s02-architecture.log`). Ten documentation
checks and 54 final completion-tracking/schema checks passed after Done updates.
Actual logs/counts are recorded in backlog verification metadata.

Independent read-only numerical review found no actionable issue and separately
ran **19 tests, zero skips**, comprising nine new-stage and ten parent tests.
Scope and limitations are retained in `build/si02-s02-independent-review.json`
and backlog verification metadata. Knowledgeable human numerical review before
release remains required. Full release tests were not rerun; previous provider
connection failures remain [unresolved](SI07_CAPACITIVE_NETWORK_TRANSIENT.md).
No clean release qualification is claimed.

## Physical and multiphysics limits

This is a supplied uniform two-conductor effective distributed-circuit model
with constant R'/L'=G'/C'=kappa, zero initial history, continuous zero-start PWL
sources and finite nonnegative resistive ends. Its exact distortionless
telegrapher solution does not establish unconditional exact Maxwell TEM
applicability. Longitudinal conductor fields and physical loss/geometry require
separate applicability evidence. General R/G values are not silently projected.

Named positions, source/constitutive identity and separate electrical loss
channels preserve later coupling inputs. W/m is loss rate, J/m is storage and
signed VI is transport. Conductor-loop loss has no individual-conductor heat
split, and dielectric loss has no volumetric mapping. No thermal deposition,
temperature/material feedback, arbitrary or frequency-dependent RLGC,
skin/proximity/dispersion, multiconductor/branched topology, geometry extraction,
nonzero history, general terminations, measured validation or qualification is
established by this stage.
