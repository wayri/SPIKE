<!-- SPDX-License-Identifier: Apache-2.0 -->
# Distributed lossless TEM line transient: SI02-S01

Experimental, production-unqualified. This solver propagates causal traveling
waves along one uniform lossless two-conductor TEM line, including repeated
reflections, two explicitly driven resistive boundaries and named interior
probes. It represents distributed delay directly, without a rational delay
approximation or time mesh. It does not perform geometry extraction or complete
the SI02 channel-extraction capability.

## Physical model and independently derived solution

The caller supplies line length ell [m], differential loop inductance per
length Lp [H/m] and interconductor capacitance per length Cp [F/m], all positive.
The cross-section and constitutive parameters are uniform and independent of
frequency/time. Line conductor resistance and dielectric conductance are zero.
One conductor carries I in the left-to-right direction, the return carries -I.
The lossless telegrapher equations are:

```
dV/dx = -Lp*dI/dt
dI/dx = -Cp*dV/dt
Z0 = sqrt(Lp/Cp)
v = 1/sqrt(Lp*Cp)
tau = ell/v
```

The line is initially unenergized, with zero waves before local t=0. Both source
voltages are continuous piecewise linear (PWL), beginning at exact (0 s, 0 V),
and ending at the same positive horizon T. This excludes an instantaneous step
at initialization, nonzero initial distributed state and inferred source
prehistory. Piecewise constant voltage after a finite ramp is supported within
the supplied horizon. No periodic extension or extrapolation occurs.

Let F(t) be the forward voltage launched at the left and B(t) the backward
voltage launched at the right. For source voltage Us and resistance R at either
end, KVL is `Us=V+R*I_into`. The right-end current into the line is the negative
of the left-to-right line current. Substituting incident/reflected wave
voltages into KVL independently yields:

```
alpha_left  = Z0/(Rleft+Z0)
alpha_right = Z0/(Rright+Z0)
gamma_left  = (Rleft-Z0)/(Rleft+Z0)
gamma_right = (Rright-Z0)/(Rright+Z0)
F(t) = alpha_left*Uleft(t) + gamma_left*B(t-tau)
B(t) = alpha_right*Uright(t) + gamma_right*F(t-tau)
```

Every substituted term retreats by tau>0. With zero negative-time history,
the expansion terminates after finitely many reflections for every admitted
observation. Iterative substitution therefore solves the causal boundary
problem without an asymptotic series approximation. For example, when only
the left source drives:

```
F(t) = alpha_left * sum_m (gamma_left*gamma_right)^m * Uleft(t-2*m*tau)
B(t) = gamma_right * F(t-tau)
```

Only nonnegative retarded source arguments contribute. The implementation uses
the alternating-boundary expansion, also supporting simultaneous right drive.
At a probe fractional position q=x/ell:

```
vf = F(t-q*tau)
vb = B(t-(1-q)*tau)
V = vf+vb
I_left_to_right = (vf-vb)/Z0
p = V*I_left_to_right                 [W, signed rightward transport]
u = 0.5*Cp*V^2 + 0.5*Lp*I^2         [J/m, stored energy density]
```

At the left end `I_into=I`; at the right `I_into=-I`. Each terminal reports
raw `Us-V-R*I_into` residual and `R*I_into^2` resistor power. Lossless interior
energy obeys `du/dt + dp/dx=0` on smooth segments. Equivalently
`u=Cp*(vf^2+vb^2)`, because the wave cross terms cancel. Stored line energy and
transported power are distinct from terminal resistor heating.

## Reviewed references and original lineage

Reviewed 18 October 2026: David H. Staelin, *Electromagnetics and Applications*
(2011):

- Chapter 8, section 8.1.1, equations (8.1.1)–(8.1.12), printed pages 229–231:
  lossless telegrapher equations, wave delay and Thevenin launching; section
  8.1.2, equations (8.1.14)–(8.1.16) and the discussion on printed pages
  232–233: resistive reflection and propagation of reflected transients.
  [Official MIT chapter 8](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
- Chapter 7, section 7.1.2, equations (7.1.7), (7.1.16)–(7.1.23), printed pages
  187–190: real instantaneous wave/current, transported power and positive
  electric/magnetic energy per length.
  [Official MIT chapter 7](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/790b8f65328723ec194cb440b303f8fb_MIT6_013S09_chap07.pdf).

The two driven-end recursion, finite causal expansion, current orientations,
probe/energy formulas and numerical admission above are independently authored
from these foundations. No external code, figures or example data were copied.
Existing finite-JSON helpers are reused; there is no fitted-network execution,
new dependency, spatial mesh or time integrator.

## API, source identity and workflow

Worker method `run_lossless_line_transient` accepts exactly `{'request': ...}`.
Request contract `spike/lossless-line-transient-request/v1` has exactly
`contract`, `length_m`, `inductance_h_per_m`, `capacitance_f_per_m`,
`left_boundary`, `right_boundary`, `probes`, `output_times_s`.
Each boundary is exactly `{resistance_ohm, voltage_points}`; resistance is finite
and nonnegative, points are 2–1024 exact `{time_s, voltage_v}` records. Times
strictly increase from zero to a common positive T, with initial voltage zero.
An explicitly zero source represents a load; a missing boundary is not inferred.
Finite zero resistance supports an ideal voltage source/short termination.
Infinite resistance/open termination is not part of this contract.

Provide 1–32 probe records `{id, fractional_position}`. Ids are unique nonblank
strings of at most 128 characters; fractional positions lie in [0,1], including
the two terminals. Probe order and identities are retained. Provide 1–1024
strictly increasing finite observation times in [0,T].

Result contract `spike/lossless-line-transient-result/v1` retains the exact
original `source_request`, canonical original-request SHA-256 `input_digest`,
derived Z0/delay/speed, reflection coefficients, observations and diagnostics.
Each observation includes `boundary_values.left/right` with source/terminal
voltage, current into line, resistor power and signed KVL residual, plus ordered
`probe_values` with both traveling voltages, total V/I, signed transported power
and energy density. No derived heat map or spatial E/H field is invented.

Strict 2020-12 request/result schemas are registered in `schemas/manifest.json`;
runtime additionally checks cross-field timing, source and identity constraints.
The canonical digest convention is sorted compact UTF-8 JSON, non-ASCII
preserved, with nonfinite values forbidden. Run the original 5-m, 50-ohm line
with 25/100-ohm terminations and a finite 1-V ramp:

```powershell
.venv/Scripts/python.exe examples/lossless_line_transient/run_line.py
```

## Numerical analysis and resource admission

Inputs and derived physical constants use checked binary64 arithmetic.
Z0 is formed as `sqrt(Lp)/sqrt(Cp)`; slowness as `sqrt(Lp)*sqrt(Cp)` and delay
as length times slowness. Terminal reflection/launch factors use scaled R/Z0
arithmetic. Physical products use separated mantissa/exponent evaluation to
avoid avoidable intermediate overflow. Nonfinite values or lost nonzero
physical products are rejected rather than truncated or regularized.

The admitted binary64 times, probe fractions and derived delay are represented
as exact standard-library fractions for retarded-time ordering and subtraction.
This avoids cumulative floating subtraction shifting an arrival across a source
knot. The returned physical delay itself remains binary64, not an exact real
measurement. PWL weights are converted to binary64 only after exact interval
selection; a collapsed strictly interior weight rejects the request. Finite
weighted sums use compensated addition. No bounce coefficient is discarded
because it is merely small; nonzero underflow fails instead.

Before evaluation, full source/probe/time admission precedes the preflight
maximum depth `floor(T/tau)`, capped at 4096, and conservative all-observation,
probe, terminal and bounce work capped at 100 million. Request/result limits
are 8/16 MiB with complete output preflight and an actual final size check.
`maximum_bounce_depth` is this horizon-based preflight depth, even if matched
terminations make the actual nonzero expansion much shorter. `estimated_work`
is a bounded operation estimate, not measured runtime. Cancellation is checked
within bounce loops; failure returns no successful partial result.

Terminal KVL acceptance is `2e-10 V + 1e-9*scale`, with scale the largest
magnitude of source voltage, terminal voltage and resistor drop. Finite horizon
permits full reflection at ideal zero-R boundaries. This is not an asymptotic
stability certificate: a repeatedly driven lossless cavity can accumulate
energy, and unresolved magnitude/resource limits still reject.

Verification uses matched delayed finite ramps, independent geometric multiple
reflections, both-end drives, exact pre-arrival zero history, current signs,
power/local-energy identities, unit scaling and shared-sample refinement.
Physical voltage/current acceptance is 2e-10 SI absolute plus 1e-9 relative;
energy/power-specific tolerances remain explicit in the independent tests.
Adding observations does not change the continuous source or computed values
at shared times. No mesh/time-step convergence is claimed because no such
discretization is introduced. See the
[executed record](validation/SI02_LOSSLESS_LINE_TRANSIENT.md).

## Multiphysics boundaries and remaining scope

Length, supplied constitutive parameters, terminal orientation and named probe
positions preserve the line's identity for later electrical/field/mechanical
coupling. Positive Lp/Cp define a classical mathematical TEM model; they do not
establish an actual material's broadband dispersion, wave speed or geometry.
The user must qualify those assumptions for a real structure.

Local J/m is stored electromagnetic energy, not a deposited heat source.
Terminal resistor watts retain explicit end ownership; distributed conductor
and dielectric heating are zero by model assumption. Whole-line energy/work
integration, thermal mapping, temperature-dependent materials, arbitrary initial
wave history, lossy/dispersive lines, multiconductor coupling, branches, layer
changes, return-path/connector discontinuities, geometry extraction, mixed-mode
calibration and measured validation remain separate stages. Knowledgeable human
numerical review before release remains required; SI02 and full PI/SI parity
remain incomplete.
