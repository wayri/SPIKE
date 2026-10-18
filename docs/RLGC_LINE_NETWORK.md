<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied uniform sampled RLGC line network: SI02-S03

Experimental, production-unqualified. This stage produces a sampled two-port
network from positive uniform L/C/length and independent nonnegative R/G at
each supplied frequency. It removes the Heaviside restriction of the
[distortionless transient](DISTORTIONLESS_LINE_TRANSIENT.md) for frequency-domain
execution. No time-domain transform, material extraction or broadband causality
qualification is implied by sampled execution.

## Reviewed governing physics

Reviewed 18 October 2026: David H. Staelin, *Electromagnetics and Applications*
(2011), chapter 8, section 8.3.1, equations (8.3.3)-(8.3.10), printed pages
249-250, for lossy phasor telegrapher laws, propagation and complex line
impedance; equations (8.3.11)-(8.3.12) for the Heaviside comparison limit.
[Official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
The source explicitly warns that conductor resistance creates longitudinal E:
these effective distributed-circuit laws are not an unconditional pure-TEM
Maxwell solution. Geometry, frequency range and modest-loss applicability need
independent physical evidence.

With e^(j*omega*t) convention, differential series z=R+j*omega*L [ohm/m]
and shunt y=G+j*omega*C [S/m] obey dV/dx=-z*I, dI/dx=-y*V.
Spatial current I is positive left to right. Terminal currents enter the line,
so the right terminal current is -I(length). At a common real reference r,
define power waves a=(V+r*I_into)/(2*sqrt(r)) and
b=(V-r*I_into)/(2*sqrt(r)); b=S*a, receiver row/source column.
Peak phasor average input power is (||a||²-||b||²)/2. No excited field or heat
value is inferred from an unexcited S matrix.

## Independent two-port derivation

Normalize spatial coordinates by length ell and current by r. Let
A=ell*z/r, B=ell*y*r (both dimensionless), u=sqrt(A)*sqrt(B), choosing the
passive branch Re(u)>=0, Im(u)>=0 for admitted nonnegative parameters/frequency.
For roots sqrt(A)=p+j*q and sqrt(B)=r+j*s, directly forming p*r-q*s
would subtract nearly equal terms on a low-loss line. The implementation uses
the independently derived positive sum
Re(u)=Re(A)*r/(p+q)+Re(B)*q/(r+s), with Im(u)=p*s+q*r.
This follows from p-q=Re(A)/(p+q) and r-s=Re(B)/(r+s), retaining weak
attenuation without a difference of large positive products.
The spatial matrix squares to u² times the identity. Its exponential gives
the voltage/current chain matrix with diagonal cosh(u), off-diagonals
A*sinh(u)/u and B*sinh(u)/u. Applying the terminal-wave relations yields

```
d0 = 2*cosh(u) + (A+B)*sinh(u)/u
S11 = S22 = (A-B)*sinh(u)/u / d0
S12 = S21 = 2/d0
```

To avoid exponentially growing intermediates, independently multiply numerator
and denominator by exp(-u). With q=exp(-u), h=(1-exp(-2u))/(2u):

```
d = 1+q²+(A+B)*h
S11 = S22 = (A-B)*h/d
S12 = S21 = 2*q/d
```

Evaluate h by complex expm1 for small u rather than subtracting near-unity
exponentials. At u=0, h=1 and q=1 give analytic DC thru, series resistance or
shunt conductance without 0/0 characteristic impedance. At DC with R and G
positive, u=ell*sqrt(R*G) is real. No DC is inferred from positive-frequency
samples. Lossless matched lines have zero reflection and transmission
exp(-j*omega*ell*sqrt(L*C)); Heaviside matched lines multiply it by
exp(-kappa*ell*sqrt(L*C)). General sampled R/G yield complex impedance and
frequency-dependent attenuation/phase without imposing that special ratio.

For nonnegative R/G, integrating the phasor power identity gives nonnegative
loss, hence S is a contraction at each sample. Reciprocity and equal end
references give S12=S21; uniform symmetry gives S11=S22. These are numerical
admission invariants, not proof of physical broadband causality.

## Numerical controls and verification

No spatial mesh or frequency interpolation is used by the production evaluation.
Binary64 arithmetic and complex exponentials remain approximate. Stable scaled
waves avoid hyperbolic overflow; representability admission bounds Re(u)<=350
and |Im(u)|<=1e6 radians. Underflow, nonfinite required operations,
ill-conditioned denominators and failed invariants reject; no passivity repair,
clipping or regularization is performed. Singular-value excess must be <=1e-9;
reciprocity error <=1e-10. Input/output bounds and cancellation prevent unbounded
execution. Exact numerical controls and actual measurements are retained in
[stage verification](validation/SI02_RLGC_LINE_NETWORK.md).

The normalized denominator magnitude must exceed 1e-12 times the sum of its
term magnitudes. At most 1024 two-by-two matrices bound work and output growth;
finite-JSON snapshot and actual response limits are 8/16 MiB. Cancellation is
polled during admission, per frequency and before return. Original types are
checked before JSON conversion; frequencies that collapse under binary64
conversion reject. No nominal mesh/frequency convergence setting can recover
an unrepresentable single-sample calculation.

Independent checks solve the spatial state transition with matrix exponentials
and boundary wave equations, and demonstrate convergence of a finite lumped
series/shunt ladder. Analytic DC, matched delay/attenuation, reference/scaling,
grid refinement, reciprocity/passivity and adversarial inputs provide additional
oracles. These use independently authored synthetic fixtures and preset
tolerances. No external implementation, text, figures or dataset was copied;
the mathematical derivation, code, examples and tests are SPIKE originals.

## Contract and workflow

Worker method `build_rlgc_line_network` accepts exactly `{'request': ...}`.
Request `spike/rlgc-line-network-request/v1` has exactly `contract`, `length_m`,
`reference_impedance_ohm`, `inductance_h_per_m`, `capacitance_f_per_m`, `samples`.
Each of 1..1024 ordered samples has exactly `frequency_hz`,
`resistance_ohm_per_m`, `conductance_s_per_m`. Frequencies strictly increase;
zero is allowed. Values are finite non-Boolean SI scalars; lengths/reference/L/C
are positive, frequency/R/G nonnegative. Independent R/G samples remain supplied
parameters: neither causality nor a dispersive material law is inferred.

Result `spike/rlgc-line-network-result/v1` retains full original `source_request`,
canonical SHA-256 `input_digest`, experimental status, `production_qualified=false`,
`network`, `diagnostics` and `limitations`. The network has digest-derived `id`,
`port_names=['left','right']`, scalar common `reference_impedance_ohm`,
`frequencies_hz` and `s_parameters` containing 2x2 complex `{real,imag}` matrices.
It can enter the existing sampled resampling/analysis path without recasting
ports or units. Further interpolation/fitting has its own admission and evidence.
Diagnostics contain sample count, maximum sampled singular-value excess above
one and maximum reciprocity error. No successful partial result is returned.

Run the independently authored 5-m example:

```powershell
.venv/Scripts/python.exe examples/rlgc_line_network/run_line.py
```

Strict 2020-12 request/result schemas are registered. Frequency ordering,
cross-field counts, finite numeric admission and numerical conditioning are
also enforced by the runtime. Malformed or numerically unrepresentable models
return structured errors; revise the supplied model/range rather than treating
failure as a valid zero network.

## Multiphysics ownership and limits

The original per-length constitutive table and length retain model identity for
later extraction, material laws and coupling. This stage computes unexcited
terminal networks; it does not assign conductor/dielectric heat, integrate loss,
map volume, or apply temperature feedback. Nonnegative samples alone do not
prove a causal broadband material response. Constant L/C and sampled R/G omit
general complex dispersive constitutive laws, coupled conductors, branches,
return paths and discontinuities. Geometry extraction, skin/proximity law
identification, excited fields/thermal transfer, measured correlation and human
numerical release review remain separate. SI02 and full PI/SI parity remain open.
