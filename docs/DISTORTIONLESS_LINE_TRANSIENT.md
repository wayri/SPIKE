<!-- SPDX-License-Identifier: Apache-2.0 -->
# Distortionless lossy line transient: SI02-S02

Experimental, production-unqualified. This solver adds constant distributed
resistance and conductance under the explicit Heaviside condition to the
[uniform line baseline](LOSSLESS_LINE_TRANSIENT.md). Delayed waves attenuate on
each flight, including reflections and interior probe legs. Conductor and
dielectric loss densities remain separate from transported power and stored
energy. General lossy/dispersive extraction and SI02 parity remain open.

## Governing model and independent derivation

For the baseline length ell [m], inductance Lp [H/m] and capacitance Cp [F/m],
the caller supplies one finite nonnegative rate kappa [1/s]. Define:

```
Rp = kappa*Lp                     [ohm/m, differential series resistance]
Gp = kappa*Cp                     [S/m, interconductor leakage conductance]
Z0 = sqrt(Lp/Cp)                  [ohm]
v = 1/sqrt(Lp*Cp)                 [m/s]
tau = ell/v                      [s]
alpha = kappa/v                  [neper/m, voltage attenuation]
```

This imposes `Rp/Lp=Gp/Cp=kappa`; independent R/G values are not accepted or
projected onto that condition. Constant ohmic R/G are assumed. Skin/proximity
effects, frequency-dependent dielectric loss and temperature laws are absent.
The effective lossy telegrapher equations are:

```
dV/dx = -Rp*I - Lp*dI/dt
dI/dx = -Gp*V - Cp*dV/dt
```

Let F(t) launch from the left and B(t) from the right. Independent substitution
shows that `f(x,t)=exp(-alpha*x)*F(t-x/v)` and
`b(x,t)=exp(-alpha*(ell-x))*B(t-(ell-x)/v)` satisfy these equations with
`V=f+b`, `I=(f-b)/Z0`. For example,
`df/dx=-alpha*f-(1/v)*df/dt`; using `alpha*Z0=Rp` and `Z0/v=Lp` produces the
first telegrapher equation. The backward wave and second equation follow with
the opposite propagation sign. Thus each single wave keeps its temporal shape
while losing amplitude; weighted reflected superpositions can still change the
observed total waveform.

The two resistive boundary relations retain the baseline launch/reflection
factors `a_left/right=Z0/(Rleft/right+Z0)` and
`g_left/right=(Rleft/right-Z0)/(Rleft/right+Z0)`. Define A=exp(-kappa*tau):

```
F(t) = a_left*Uleft(t) + g_left*A*B(t-tau)
B(t) = a_right*Uright(t) + g_right*A*F(t-tau)
vf(q,t) = exp(-kappa*q*tau)*F(t-q*tau)
vb(q,t) = exp(-kappa*(1-q)*tau)*B(t-(1-q)*tau)
```

Positive delay and zero prehistory terminate the alternating launch expansion
after a finite number of reflections. A complete round trip multiplies a wave
by `g_left*g_right*A^2`. No fitted delay, temporal mesh or frequency transform is
introduced. At kappa=0 all baseline point fields retain exactly the lossless
solver's values, and new distributed-loss fields are exactly zero.

The named probes retain real instantaneous V/I, signed `p=V*I` [W] and
`u=(Cp*V^2+Lp*I^2)/2` [J/m]. Distributed losses are:

```
q_conductor = Rp*I^2             [W/m]
q_dielectric = Gp*V^2            [W/m]
q_total = q_conductor+q_dielectric = 2*kappa*u
du/dt + dp/dx = -q_total
```

The energy identity follows by multiplying the first telegrapher equation by I,
the second by V, adding and applying the product rule. It is a real
instantaneous identity; no RMS/phasor factor 1/2 applies to Rp*I² or Gp*V².
Terminal resistor power is separate from distributed line losses.

## Reviewed references and physical applicability

Reviewed 18 October 2026: David H. Staelin, *Electromagnetics and Applications*
(2011), chapter 8, section 8.3.1, equations (8.3.1)–(8.3.12), printed pages
249–250, for lossy telegrapher laws, propagation impedance and the distortionless
condition; equation (8.3.16), printed page 251, identifies resistive/leakage loss
in phasor time-average notation. The instantaneous energy/loss formulation above
is independently derived from the time-domain equations. Section 8.1 supplies
the parent launching and reflection foundations.
[Official MIT chapter](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).

The source also states that finite wire resistance introduces longitudinal E,
so an effective lossy telegrapher model is not an unconditionally exact TEM
Maxwell solution. This implementation solves the declared distributed-circuit
model; applicability of the quasi-TEM/modest-loss assumptions to a real geometry
requires separate evidence. Large mathematically admitted kappa does not
establish physical model accuracy.

The two-ended attenuated recursion, local loss checks and numerical admission
are independently authored from these foundations. No external source code,
figures or example data were copied. Parent finite-JSON/PWL/timing/product
helpers are reused without changing the old solver or adding a dependency.

## Contract and executable workflow

Worker method `run_distortionless_line_transient` accepts exactly
`{'request': ...}`. Request contract
`spike/distortionless-line-transient-request/v1` has exactly `contract`,
`line_request` and `attenuation_rate_per_s`. The nested baseline v1 line request
supplies Lp/Cp/length, sources, boundaries, probes and output controls. Its
contract identifies the reused baseline data shape; the outer contract and
rate define the lossy model being executed. It does not execute or pretend to
retain a separate lossless run.

All baseline requirements apply: positive uniform Lp/Cp/length, zero initial
line history, continuous PWL sources beginning at (0,0), common positive finite
horizon, finite resistive boundaries including zero, named fractional probes
and increasing observations. Arbitrary initial waves, ideal infinite-R opens,
reactive/nonlinear ends and inferred missing loads remain unsupported.

Result contract `spike/distortionless-line-transient-result/v1` retains the exact
full outer `source_request` and canonical original-request SHA-256 digest,
baseline impedance/delay/speed/reflection fields, plus `resistance_ohm_per_m`,
`conductance_s_per_m`, `attenuation_neper_per_m` and
`one_way_voltage_attenuation`. Each ordered probe adds
`conductor_loss_w_per_m`, `dielectric_loss_w_per_m`, `total_loss_w_per_m` to
the existing waves/V/I/power/energy fields. Terminal signs, KVL residuals and
resistor power remain unchanged in meaning. Diagnostics retain depth/work/KVL
and add `maximum_local_loss_balance_residual_w_per_m` as a raw absolute value.

Strict registered 2020-12 schemas and runtime admission preserve identities,
units and finite values. Digests use sorted compact UTF-8 JSON with non-ASCII
preserved and nonfinite numbers forbidden. Run the original 5-m, 50-ohm line
with kappa=1e7/s, hence Rp=2.5 ohm/m, Gp=0.001 S/m and alpha=0.05 neper/m:

```powershell
.venv/Scripts/python.exe examples/distortionless_line_transient/run_line.py
```

## Numerical analysis, bounds and verification

Exact standard-library fraction arithmetic preserves retarded-time ordering
relative to admitted binary64 times, positions and derived delay. PWL amplitudes
and exponentials remain binary64 quantities. Each reflected flight includes
one complete A factor; probe-leg attenuation uses its actual fractional travel
time. Zero rate or zero travel has exact factor 1. For positive rate/travel,
nonfinite/zero exponents, exp underflow or absorption of attenuation at unity
reject rather than silently producing a lossless or zero wave. Nonzero product
underflow also rejects; no small reflection tail is deliberately truncated.

Full baseline and loss-derived admission, depth<=4096, combined wave/loss work
<=100 million and full nested output estimate precede wave evaluation. Request/
result limits remain 8/16 MiB, with final actual byte validation. Cancellation
is checked within bounce loops. Failure returns no successful partial result.
The reported depth remains the baseline horizon preflight bound, including
matched cases whose actual nonzero bounce chain is shorter.

The actual local sum of losses is compared with independently evaluated
`2*kappa*u`: relative residual must be <=1e-10 when nonzero, and both-zero
identities must remain exact. The maximum absolute residual is retained, not
redistributed. Parent terminal KVL retains 2e-10 V absolute plus 1e-9 relative
scale admission. Numerical agreement does not certify arbitrary conditioning
or physical model uncertainty.

Independent references include attenuated matched ramps, geometric echo series,
both-end sources, smooth-wave telegrapher derivatives, exact zero-loss reduction,
unit/refinement checks and a matched finite-pulse energy budget. That budget
distinguishes generator work, source-resistor heat, network injection, remaining
line storage, right-end outflow and distributed dissipation using independent
space/time quadrature. It does not add a production continuous-energy API.
Preset observable-specific tolerances and actual results are in the
[execution record](validation/SI02_DISTORTIONLESS_LINE_TRANSIENT.md).

## Multiphysics ownership and remaining scope

Conductor/dielectric W/m are electrical loss rates; J/m remains stored energy.
Rp represents total differential conductor-loop resistance, so splitting that
heat among individual conductors requires supplied geometry/material ownership.
Likewise Gp loss does not specify a volumetric dielectric distribution. Named
probe positions, full parameters and separate loss channels retain evidence for
a later conservative mapping; this stage performs no thermal deposition,
temperature feedback or material-law lookup.

Arbitrary non-Heaviside R/G, frequency-dependent RLGC/skin/proximity/dispersion,
multiconductor coupling, branches, geometry/return/discontinuity extraction,
nonzero distributed state, general terminal models, continuous production
energy/heat ledgers and measured qualification remain separate gates.
Knowledgeable human numerical review before release remains required. SI02 and
full PI/SI parity remain incomplete.
