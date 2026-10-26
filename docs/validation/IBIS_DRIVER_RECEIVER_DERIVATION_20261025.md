<!-- SPDX-License-Identifier: Apache-2.0 -->

# Classic IBIS driver/receiver: independent derivation, 25 October 2026

Status: experimental formulation; no numerical execution or hardware validation
is claimed by this document. Knowledgeable human numerical review remains
required before release. This record was independently authored from the
primary documents below before review of the new implementation. No external
solver implementation, sample circuit, vendor model or test dataset was copied.

This is the preimplementation evidence for a bounded single-ended behavioral
ngspice export. It supplements [the evidence policy](../NUMERICAL_METHOD_EVIDENCE.md).
Implementation, compiled-backend acceptance, and measured validation are
separate gates. Existing inventory/DC-slope/ramp behavior is not qualified by
this derivation.

## Source ledger and source facts

| Primary source | Exact reviewed extent on 2026-10-25 | Use and limits |
| --- | --- | --- |
| IBIS Open Forum, [IBIS Version 8.0](https://ibis.org/ver8.0/ver8_0.pdf), ratified 2025-12-05 | Section 3.2 p.19; section 5 pp.35-36; section 6.1 pp.64, 81-84, 91-93, 107-108; section 9 p.205. Public PDF text, including the current-direction, table-axis, waveform, capacitance and package clauses; not an all-keyword conformance review. | Reference conventions and data semantics; not an implementation or validation certificate. |
| Vogt, Atkinson, Warning and Nenzi, [Ngspice User's Manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf), version 47+ development edition, 2026-09-28 | Sections 5.1.1, 5.1.2, 5.1.4 pp.107-114 and 11.3.10 pp.337-338; public PDF text. | Behavioral current expressions, time, piecewise linear evaluation and transient controls. Exact installed executable/version compatibility remains to be tested. |

IBIS specifies currents into the component; pullup/power-clamp axes are
rail minus output. Clamps remain present while output tables are enabled
selectively. Waveforms include die capacitance, retain their common stimulus
time, and begin/end at DC values. Pin RLC overrides package defaults. Ordinary
C_comp min/max entries order magnitude, independently of process corner.
Advanced C Comp Corner has different semantics and is excluded here.

The ngspice manual establishes expression-defined current sources and time/PWL
evaluation. Its PWL function extrapolates beyond supplied endpoints; this
export therefore needs its own source-domain acceptance guard. The maximum
transient step is distinct from the reporting increment.

All tolerances, rejection choices, derivations and proposed oracles below are
SPIKE engineering decisions, not numerical requirements asserted by those sources.
Primary-document access does not grant redistribution rights to their examples
or to manufacturer IBIS files. Such files need their own provenance.

## Bounded physical envelope

Admit classic Input receivers and Output, I/O, or 3-state drivers with fixed
ideal reference rails. I/O/3-state admit enabled low/high operation and a
static disabled state; transitions into/out of disabled state need additional
characterization and are rejected. Input is a passive electrical loading model,
not a fabricated digital receiver/BER model.

Retain the entire selected pullup, pulldown, ground-clamp and power-clamp tables,
die capacitance and lumped selected-pin/package RLC. Absent clamp structures
contribute zero; do not invent diode laws or add a clamp already embedded in
the source output tables. Package parameters are nonnegative and finite.
No local resistance fit replaces the nonlinear current curves.

Each edge must have exactly two distinct, time-correlated resistive fixtures,
with positive finite R_fixture and explicit selected-corner V_fixture.
C_fixture, L_fixture, R_dut, L_dut and C_dut must all be zero or absent with
zero semantics. Waveform time supports must match; native internal knots may
differ. Require at least three finite, strictly increasing time samples and
verified endpoint plateaus. The same stimulus time origin is retained; never
align independently by output crossings or silently trim to an overlap.

Reject ramp-only, one-fixture, missing selected data, dynamic impedance,
power-aware/SSO/composite-current operation, ECL specialization, open-drain,
differential, AMI, external model/circuit, scheduled drivers/submodels,
dynamic clamps or termination, transit-time clamp charge, advanced C Comp
Model/Corner and advanced package/interconnect models. Unknown behavior-bearing
keywords cannot silently disappear. A smaller supported envelope is legitimate;
silently approximating an unsupported model is not.

The I-V/waveform process column, die-capacitance magnitude column and package
magnitude column are separate recorded selections. Ordinary C_comp min/max
does not automatically follow the I-V column. Never sum lumped C_comp with
split capacitances. The present scalar derivation assumes an explicitly
admitted lumped die capacitance C in farads.

## Independent conservation derivation

Let v be the die pad potential in volts. Constant reference potentials are
Vpu, Vpd, Vpc and Vgc. Define signed ampere-valued functions

```text
U(v) = I_pullup(Vpu - v)
D(v) = I_pulldown(v - Vpd)
P(v) = I_power_clamp(Vpc - v)
G(v) = I_ground_clamp(v - Vgc)
J(v) = P(v) + G(v).
```

Every current is oriented from the pad into the buffer branch. A sourcing
pullup normally has U < 0. In particular, a decreasing I_pullup table against
its rail-relative argument can describe a positive incremental output
conductance: dU/dv = -dI_pullup/dx. A negative table slope is not an invalid
negative output resistance.

Assume an empirical separated model with dimensionless time coefficients
ku(t), kd(t). Conservation of pad charge with external load current Iload
oriented out of the pad gives

```text
C dv/dt + ku U(v) + kd D(v) + J(v) + Iload = 0.       (1)
```

C_comp is removed from the fixture balance only to identify switching
coefficients, then inserted once as an actual die capacitor in the exported
circuit. Omitting it during extraction and restoring it afterward double counts
its edge effect. The passive receiver sets ku=kd=0 but retains J and C.

For fixture j, Iload=(vj-Vfj)/Rj. The two measurements at the same stimulus
time share the unknown coefficient pair, so (1) becomes

```text
A = [[U(v1), D(v1)], [U(v2), D(v2)]]
b_j = -(C dvj/dt + J(vj) + (vj-Vfj)/Rj)
A [ku, kd]^T = b.                                    (2)
```

The entries of A and b have units A; their solution is dimensionless.
For A=[[a,b],[c,d]], determinant Delta=ad-bc is in A^2.
An independent hand oracle can use
ku=(d*b1-b*b2)/Delta, kd=(a*b2-c*b1)/Delta.
Production should use a scaled small-system solve and explicitly detect
non-finite or zero determinants. Different resistors alone do not guarantee
independence: proportional rows still identify only one linear combination.

The separability assumption is an empirical hypothesis. Two fixture equations
fit two coefficients exactly and cannot validate transfer to a third load.
A held-out load and actual-engine replay are required evidence.

## Discrete derivative and its limits

For three native samples around interior time ti, let hm=ti-ti-1 and
hp=ti+1-ti. Differentiating the unique quadratic through those samples gives

```text
di = -hp/(hm*(hm+hp))*vi-1
     +(hp-hm)/(hm*hp)*vi
     +hm/(hp*(hm+hp))*vi+1.                           (3)
```

The coefficients annihilate constants and differentiate linear and quadratic
polynomials exactly. For smooth v, Taylor expansion gives leading error
hm*hp*v'''(ti)/6. Thus second-order accuracy requires bounded third derivative,
resolved smooth data and controlled spacing. Sample noise of size ev can
produce O(ev/min(hm,hp)) derivative noise; multiplying by C converts it into
current error. Interpolating more points into the same coarse data is not
source refinement and cannot establish accuracy.

Set endpoint derivatives to zero only after testing their first/last secant
capacitive currents against the reconstruction tolerance below. Interpolate
each native v and d onto the union grid while preserving time origins, solve
(2) there and linearly interpolate k. This is a declared derivative surrogate,
not the exact derivative of piecewise linear v. At every union interval
midpoint separately compare interpolated d with the actual local voltage
secant. Check KCL with that secant too. Coarse/noisy waveforms that fail are
rejected, not repaired by clipping weights or enlarging tolerances.

## Conditioning and acceptance contract

Use infinity norms and float64 arithmetic. The following defaults are
predeclared screening thresholds, not uncertainty bounds on manufacturer data.

| Quantity | Required screen |
| --- | --- |
| Relative sensitivity | kappa_inf(A)=norm(A)*norm(inv(A)) <= 1e6 |
| Absolute sensitivity | norm(inv(A))*1e-9 A <= 1e-3 |
| Algebraic residual | norm(Ak-b) <= 1e-12 A + 1e-10*(norm(A)*norm(k)+norm(b)) |
| Reconstructed current | abs(r_j) <= 1e-6 A + 1e-3*S_j |
| Matched state weights | abs(ka-kb) <= 1e-3 + 1e-3*max(abs(ka),abs(kb)), each coordinate |

Here S_j is the sum of absolute capacitive, weighted pullup, weighted pulldown,
separate clamp and fixture currents at the evaluation point; r_j is their
signed sum. The current screen applies at all union knots and midpoints, to
endpoint secant plateau currents, and to the midpoint capacitive derivative
defect. Recheck midpoint KCL with the actual PWL-v secant, not only interpolated
d. Solve residual at knots is largely algebraic; midpoint and derivative
screens address additional discretization error. None proves unseen-time
accuracy or measured data fidelity.

Absolute sensitivity closes a relative-conditioning blind spot: A=epsilon*I
has condition one while amplifying tiny current errors arbitrarily. To first
order, perturbing (2) gives delta_k=A^-1(delta_b-delta_A*k).
Therefore report both norms, residuals, maximum coefficient magnitude and
current scales; accepted condition alone does not bound coefficient error
when actual source errors are unknown. Never force ku+kd=1 or clip k into
[0,1]. Out-of-range weights are visible diagnostic evidence; well-conditioned
values alone do not establish a physically transferable model.

For source voltage/derivative error ev, ed, the row-current perturbation is
bounded locally by

```text
abs(delta_b) <= C*ed
 + (abs(G')+abs(P')+1/Rj)*ev + other_input_errors.
```

The matrix perturbation adds the U,D slope terms. This explains why sparse
samples, steep clamps and weak extraction currents are difficult independently
of the solver. No manufacturer noise model is invented.

Every source-table evaluation must lie inside its selected voltage axis.
An expression may use constant endpoint continuation solely to keep ngspice
Newton trials finite, but accepted transient states require a source-domain
audit. Reporting-grid checks alone can miss excursions; audit the returned
accepted-time trajectory, retain tmax and require timestep refinement before
qualification. A failed range check cannot produce a successful result.
Source PWL corners are continuous but have discontinuous tangents; smooth
Newton convergence is not guaranteed.

## Static calibration and edge concatenation

Solve (2) with zero derivatives separately at each endpoint pair. This yields
rising-low, rising-high, falling-high and falling-low coefficients. Do not
replace them with (0,1) and (1,0): tabulated DC mismatch, leakage or calibrated
scaling can change the extracted values.

Require low endpoints to agree and high endpoints to agree using the weight
screen. Choose rising-low and rising-high as canonical states. Snap only
already matching falling endpoints to those states, then repeat current
reconstruction. Reject incompatible states or residual failures.

A scheduled low-to-high transition uses the entire rising k waveform, including
lead-in; high-to-low uses the falling waveform. Translate the common source
time origin to the explicit input event. Hold canonical state weights before
and after each edge. Require edges to finish before another begins; reject
overlap, unsupported initial state or a high/low transition from static z.
Static z uses zero drive coefficients, not zero clamps or zero capacitance.
The input sequence denotes output state; any logical Polarity mapping must be
explicit at its boundary. Enable polarity does not supply missing enable
transition waveforms.

For fixed rails, a die-to-reference capacitor contributes C dv/dt. A simple
package realization uses series R and L between die and external pin, with
C_pkg at the external pin to the fixed reference. Resolve individual-pin
overrides first, never add override and default. This declared lumped topology
is an approximation, not package-field extraction. Avoid zero-valued R/L
elements by collapsing their series nodes. Keep die and pin observations
distinct. Package stored energy is (L*i^2+C_pkg*vpin^2)/2 and die energy is
C*v^2/2 relative to the chosen fixed reference; resistor dissipation is R*i^2.
Ideal supplies and switching sources exchange energy, so the whole driver
must not be called passive merely because its package is passive.

## Proposed independent verification and open gates

The following checks are planned acceptance evidence, not runs performed by
this derivation author.

| Independent case | Observable and predeclared acceptance |
| --- | --- |
| Analytic linear pullup/pulldown with signed sourcing, original invented parameters and two fixtures | Algebraic k within 1e-10 absolute for well-scaled exact arithmetic inputs; verify pad KCL and PU slope sign independently. |
| Constant, linear and quadratic sample polynomials on unequal grids | Equation (3) derivative within 1e-12 times a unit-aware derivative scale. Smooth cubic refinement should approach factor four error reduction on halving a uniform step. |
| Scaled identity and nearly proportional fixture matrices | Relative and absolute conditioning rejection are separately exercised; exact singular and duplicate fixtures rejected. |
| Known nonunit static states | Recover both states, preserve holds/joins, reject opposite-edge endpoint mismatch; no coefficient clipping. |
| Coarse curved or noisy waveforms | Derivative-defect/midpoint reconstruction fails when algebraic knot residual still passes. |
| Clamp, capacitor and package branches | Check sign, charge balance, nonnegative package stored energy and resistor work; ensure every branch is present once. |
| Missing selected data, bad time axes, fixture parasitics and unsupported keywords | Structured rejection; no silent typical fallback or ramp substitution. |
| Future actual ngspice replay of both extraction fixtures | Require maximum voltage error <= 1 mV + 1e-3*rail_span; repeat with tmax halved and require change <= one quarter of that tolerance. Retain executable version, deck, model/input hashes, raw accepted times and logs. |
| Future withheld resistive/reactive loads and manufacturer measurements | Separate transfer/model discrepancy and measurement uncertainty criteria must be fixed before testing. Calibration fixtures are not withheld evidence. |

The source review and original algebra above are complete. No build, numerical
test, ngspice solve, convergence study or measured comparison was run in this
documentation subtask. The implementation owner must record actual executed
evidence separately, and link this record from the governing evidence/status
documents. Missing source uncertainty, real-model applicability, timestep
convergence, held-out load performance and knowledgeable human review remain
open. An exportable netlist alone does not close any of those gates.

## Independent implementation read review, 25 October 2026

A subsequent bounded source review compared the new compiler, table extraction,
execution wrapper, IPC wrapper and tests against this previously frozen method.
The reviewer ran no build, numerical test or native solver. Test and native
execution claims from other workers must be recorded with their own receipts.

Two actionable findings were returned to the implementation owner and their
corrections were inspected in source:

- Execution accepted a null expected executable digest through the inspection
  helper's optional argument, bypassing the reviewed-byte match. The run entry
  now requires a non-optional lowercase 64-hex SHA-256 before compilation or
  launch. The no-launch regression includes null and malformed digests.
- Separate surrogate-derivative and secant KCL residuals could each pass while
  their difference exceeded the frozen direct capacitive derivative screen.
  Replay now explicitly checks C*(d_interpolated-d_secant); its independent
  regression constructs opposite small residuals with an excessive difference.
  Extraction provenance now also retains maximum inverse gain and coefficient
  magnitude.

No remaining actionable sign, calibration-state, schedule or source-domain
mismatch was found in this bounded read. Series zero-volt sources used for
zero package R/L are electrically equivalent to collapsing those series nodes
in this acyclic topology. They do not imply a changed package model.

The spatial service was reviewed only as a mapping of the existing supplied
coupled-line result. Its enforced conductor order, zero incident victim waves
at ports 1 and 3, conductor-index-1 voltage selection, co-directed segment
fraction, millimetre/metre length match and RMS labeling agree with the existing
coupled-pair owner. This establishes a source-code correspondence, not measured
coupling or PCB material extraction. Canonical input/occurrence identities are
explicit bindings supplied by the caller; physical source authenticity is not
inferred.

Reviewed snapshot SHA-256 values (paths relative to repository root):

| File | SHA-256 |
| --- | --- |
| python/spike_core/solvers/signal_integrity/receivers/ibis_behavioral.py | c1afb60e98b84327d16b0810304340f7af653216564ffd6c41a4ee6d9bc0eb50 |
| python/spike_core/solvers/signal_integrity/receivers/ibis_behavioral_tables.py | 4ef01b4c56f5d3c692fa1cf22416edade9f7b227fe1e6362902f9a961197cec7 |
| python/spike_core/solvers/signal_integrity/receivers/ibis_behavioral_execution.py | 9806294f07df9fc420d8061fbf651e8fb97d977f136e7249822a5ab2704752ce |
| python/spike_core/service_ibis_behavioral.py | ed77b85b9f78c919aaf8c978ac06a52ec7a11a22a3dc30e690d1e01683ac0fe8 |
| python/spike_core/service_si_spatial.py | f241b667b039cf231d498867c10544edfb1a269d8edbd1f0a3989eec98722af5 |
| tests/python/test_ibis_behavioral.py | 0f561d840061df0b5e1c743ce06e8dc5b5eba7f09976f21fb2c9a46c7b3e8a65 |

This agent review does not satisfy the required knowledgeable human numerical
release review, nor replace executed fixture replay and measured validation.
