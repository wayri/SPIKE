<!-- SPDX-License-Identifier: Apache-2.0 -->
# Coherently driven sampled RLGC fields and loss ledger: SI02-S04

Experimental, production-unqualified. This stage excites a
[supplied uniform sampled RLGC line](RLGC_LINE_NETWORK.md) at each positive
frequency with explicit coherent RMS incident power waves at both ends.
It returns complex interior voltage/current, signed power, average model L/C
energy density, separate conductor/dielectric loss density and integrated loss.
Every frequency is a separate steady-state operating case; no sum over sweep
frequencies, broadband time waveform or thermal deposition is inferred.

## Reviewed physics and convention

Reviewed 18 October 2026: David H. Staelin, *Electromagnetics and Applications*
(2011), chapter 8, section 8.3.1, equations (8.3.3)-(8.3.12), printed pages
249-250, and equation (8.3.16), printed page 251, for lossy phasor telegrapher
laws, propagation, characteristic impedance and conductor/leakage dissipation.
[Official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
The source uses peak phasors and a one-half time-average loss factor. This
contract uses RMS phasors: peak=sqrt(2)*RMS, so loss is R*|I|²+G*|V|².
Average model storage is .5*C*|V|²+.5*L*|I|² in J/m.

With e^(j*omega*t), z=R+j*omega*L [ohm/m], y=G+j*omega*C [S/m], the
effective distributed circuit obeys dV/dx=-z*I and dI/dx=-y*V. Spatial current
is left to right; terminal currents enter the line, making right current -I(ell).
At common positive real reference r, a=(V+r*I_into)/(2*sqrt(r)) and
b=(V-r*I_into)/(2*sqrt(r)); a,b have units sqrt(W). The signed terminal input
is Re(V*conj(I_into))=|a|²-|b|² under this RMS convention.

The underlying two-port matrix is amplitude-convention independent. Its
positive-frequency samples and names are retained unchanged; its earlier
unexcited description used peak waves. This new contract explicitly sets RMS
amplitude and never reinterprets a supplied peak amplitude as RMS.

## Independent driven-wave derivation

Let u=gamma*ell=alpha+j*beta, q=exp(-u), Zc=sqrt(z)/sqrt(y), and
zeta=Zc/r. Use the parent's passive branch and positive-sum attenuation
calculation to avoid cancellation of weak loss beside large phase. Write

```
f(x) = F*exp(-u*x/ell)
b(x) = B*exp(-u*(1-x/ell))
V(x) = f(x)+b(x)
I(x) = (f(x)-b(x))/Zc
rho = (zeta-1)/(zeta+1)
t = 2*sqrt(r)*zeta/(zeta+1)
[1, rho*q; rho*q, 1] * [F; B] = t * [a_left; a_right]
```

F launches at the left and B at the right, so every evaluated exponential
decays toward the other end. This boundary system follows directly by inserting
V and I into the two incident-wave definitions. It handles simultaneous
coherent sources; adding independent source powers would lose interference.
Signed transported power is p(x)=Re(V*conj(I)), not |V|*|I|.

The instantaneous telegrapher energy identity, averaged over a sinusoidal
period, gives dp/dx=-(R*|I|²+G*|V|²). Define per-length loss rates
qc=R*|I|² and qd=G*|V|² [W/m]. Nominal model electric/magnetic storage is
ue=.5*C*|V|², um=.5*L*|I|² [J/m]; neither is heat.

## Independent continuous spatial loss integrals

The production ledger uses analytic integrals, not a probe sum or quadrature.
For dimensionless alpha/beta from u, define

```
H = ell*(1-exp(-2*alpha))/(2*alpha)       (ell when alpha=0)
J = ell*exp(-alpha)*sin(beta)/beta       (sinc limit when beta=0)
Iv = .5*|F+B|²*(H+J) + .5*|F-B|²*(H-J)
Ii = [.5*|F-B|²*(H+J) + .5*|F+B|²*(H-J)]/|Zc|²
Pc = R*Ii
Pd = G*Iv
Ptotal = Pc+Pd
Pin = Pleft_into+Pright_into
residual = Pin-Ptotal
```

H integrates each decaying-wave magnitude and J the real cross term. Expanding
|f+b|² and |f-b|² gives these expressions. The sum/difference formulation
avoids subtracting large coherent field integrals. H-J is evaluated through
ell*exp(-alpha)*[(sinh(alpha)/alpha-1)+(1-sin(beta)/beta)], with short-argument
series to retain its small positive value. H+J and H-J are nonnegative for the
admitted passive branch. Conductor/dielectric powers are never clipped and
the balance residual is never redistributed as heat.

## Numerical admission and independent verification

The parent network admission and 350-neper/1e6-radian representation limits
apply. This stage supports positive frequencies only; DC excitation is rejected
explicitly while the parent network's DC support remains intact. The two-ended
wave solve requires condition number <=1e8 and relative residual <=1e-10.
Normalized endpoint V/I must also agree with the retained network's incident
and outgoing waves within 1e-9 of the expected-wave/incident norm scale.
Power balance tolerance is 1e-10 times the maximum of total incident power,
integrated loss and absolute net input; exact zero excitation requires exact
zero. Raw signed residuals remain reported. Near-cancellation, overflow,
underflow, failed conditioning or invariants return errors, not repaired data.
Exact implementation controls and test tolerances are in the
[verification record](validation/SI02_RLGC_LINE_FIELDS.md).

Requests allow 1..1024 frequency cases and 1..32 probes. Work is bounded by
those dimensions. Before numerical evaluation, result-size preflight is
3*request_bytes + samples*(2048+1024*probes)+65536 <=16 MiB, so not every
maximum-dimension combination is admitted. The finite-JSON snapshot limit is
8 MiB and actual full response limit 16 MiB. Cancellation is checked during
admission, nested network execution, per case/probe and before return.

Independent tests use a spatial state matrix exponential with direct terminal
wave boundary solves for V/I, and separate spatial loss quadrature. Analytic
matched-line heat, two-sided coherent interference, lossless limits, model
units/scaling, observation refinement and malformed/precision/resource controls
provide additional evidence. Production integration is analytic: quadrature is
only an independent verification oracle. All derivations, code, examples and
fixtures are independently authored; no external implementation or source data
was examined, copied or adapted. Synthetic verification is not physical
validation; knowledgeable human numerical review before release is required.

## Contract and executable workflow

Worker `run_rlgc_line_fields` accepts exactly `{'request': ...}`. Request
`spike/rlgc-line-fields-request/v1` contains exactly `contract`, `line_request`,
`excitations`, `probes`. The nested parent request supplies original L/C/length,
reference and R/G table, with a strictly positive frequency grid in this stage.
Each matching ordered excitation contains exactly `frequency_hz`,
`incident_left`, `incident_right`; complex values use `{real,imag}`. Grids must
match exactly; no interpolation is implicit. Probes have a unique bounded
`id` and `fractional_position` in [0,1]. JSON numbers are finite non-Boolean
scalars; named quantities and units are enforced at the runtime boundary.

Result `spike/rlgc-line-fields-result/v1` retains the complete original
`source_request`, canonical SHA-256 `input_digest`, compatible parent `network`,
`points`, `diagnostics`, `limitations`, experimental status and
`production_qualified=false`. Each point retains `frequency_hz`, `boundary_values`
with complex RMS voltage/current and signed input watts, ordered `probe_values`
with complex V/I, signed transported watts, electric/magnetic J/m and separate
conductor/dielectric/total W/m, and `power_balance` with signed net input,
integrated conductor/dielectric/total watts and raw signed residual.
Diagnostics retain sample/probe count and maximum absolute power residual.
Strict 2020-12 schemas are registered; cross-field identity and numerical checks
are also runtime requirements. Failed admission returns no partial success.

```powershell
.venv/Scripts/python.exe examples/rlgc_line_fields/run_line.py
```

The original 5-m example applies coherent complex waves at both ends across
three supplied frequencies. Each point is an independent steady-state result.

## Multiphysics ownership and remaining scope

R is differential conductor-loop resistance; its integrated loss cannot be
split between conductors without supplied geometry/material ownership. G loss
does not define a dielectric volume distribution. Named positions, original
constitutive/excitation identity and separate integrated loss channels preserve
later conservative transfer inputs. This stage executes neither thermal
deposition nor temperature feedback, nor a spatial thermal mesh.

Constant nominal L/C storage is a property of this effective circuit model,
not a general dispersive-material energy law. Nonnegative sampled R/G do not
establish broadband causality, physical quasi-TEM applicability or measured
accuracy. General complex constitutive dispersion, coupled conductors,
branches/returns/discontinuities, geometry/material extraction, transient/DC
fields and production qualification remain separate. SI02 and full PI/SI
parity remain open.
