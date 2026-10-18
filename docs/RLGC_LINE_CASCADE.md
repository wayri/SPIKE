<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied piecewise RLGC cascade: SI02-S05

Experimental, production-unqualified. Ordered uniform scalar line sections
may have different supplied lengths and L/C/R/G values. Adjacent ends share
an explicit ideal zero-length electrical junction. A simultaneous wave solve
includes all interface reflections and returns a two-port network, coherent
per-section fields/losses and a checked global electrical loss ledger.
This extends [uniform driven fields](RLGC_LINE_FIELDS.md) without changing
their numerical implementation or assigning inferred PCB geometry.

## Reviewed foundation and independent connection derivation

Reviewed 18 October 2026: Staelin, *Electromagnetics and Applications* (2011),
chapter 8 section 8.1.2, equations (8.1.14)-(8.1.16) and the interface discussion
on printed pages 232-234, for reflection and continuity of voltage/current
between different line impedances. Section 8.3.1, equations (8.3.3)-(8.3.12)
and (8.3.16), printed pages 249-251, supplies lossy phasor propagation and
dissipation. [Official MIT text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
Only these mathematical foundations were used; no external source code,
figures, examples or datasets were copied or adapted.

All sections use the same positive real power-wave reference r and exactly
the same positive-frequency grid. With RMS waves,
V=sqrt(r)*(a+b), I_into=(a-b)/sqrt(r). Connecting right end p to left end q
requires Vp=Vq and I_into,p=-I_into,q. Adding/subtracting these relations
gives ap=bq and aq=bp. The shared r is a wave coordinate; actual characteristic
impedances may differ. No renormalization is inferred.

Let W be the block-diagonal matrix of admitted section S matrices, C swap
each internal adjacent pair and have zero external rows, and U inject the two
external incident waves. Then

```
b = W*a
a = C*b + U*a_external
(I-C*W)*a = U*a_external
S_external = select_external(W*solve(I-C*W,U))
```

Solve the two basis excitations together. Their coherent linear combination
gives the incident waves at every section, including repeated reflections.
Pass those actual local incident waves to the unchanged uniform field solver.
Do not multiply long growing chain matrices in production. Independent tests
use physical spatial matrix exponentials and chain multiplication as a separate
moderate-condition oracle.

## Conservation and multiphysics ownership

Each parent field result retains RMS V/I, signed terminal/transported power,
nominal average L/C storage [J/m], local conductor/dielectric loss [W/m] and
analytic continuous spatial loss [W]. For each interface, retain complex
Vp-Vq and I_into,p+I_into,q, and signed P_into,p+P_into,q. Ideal junctions
contain neither resistance nor storage; their flux cancels in the global sum.

```
P_external = ||a_external||² - ||S_external*a_external||²
P_conductor = sum(section conductor loss)
P_dielectric = sum(section dielectric loss)
P_heat = P_conductor+P_dielectric
residual = P_external-P_heat
```

Every section's heat is counted once. Internal transported watts are not added
as heat. Raw interface/global residuals are retained; no clipping, passivity
repair, residual redistribution or inferred heat split is performed. Original
section IDs, line requests, probes and global excitations remain in the outer
source request. Child field requests record the local excitations actually
computed by the connection solve; they are not independent measured sources.
Conductor-loop and dielectric heat retain distinct ownership for later thermal
mapping, which is not executed here.

## Admission, precision and resources

Support is 1..8 sections, 1..1024 positive-frequency cases and 1..32 probes per
section, subject to aggregate limits. IDs are unique and bounded. Grids and
references must match exactly; incompatible values, DC, unknown fields,
Booleans and nonfinite numbers reject before numerical execution.
The two-ended connection matrix must have condition <=1e8 and scaled solve
residual <=1e-10. Sampled external passivity and reciprocity remain admitted
numerical invariants. Parent 350-neper/1e6-radian propagation controls and
field conditioning/precision admission remain in force.

Interface voltage/current tolerances are 1e-9 relative to the admitted
wave/field scale. Interface and global power checks use 1e-10 of the declared
incident/heat/terminal-power scale, with exact zero for a zero scale. Actual
controls and numerical errors are retained in the
[verification record](validation/SI02_RLGC_LINE_CASCADE.md).

Before any parent network solve, bound work by
samples*((2*N)^3+64*N+32*total_probes)<=100 million and predicted full nested
output by 5*request_bytes+samples*(4096+4096*N+1536*total_probes)+65536<=16 MiB.
Finite-JSON input is at most 8 MiB; actual complete output is also bounded by
16 MiB. Not every maximum-dimension combination is admitted. Cancellation
propagates through connection, parent network/field and output execution.
Failed conditioning, precision, budget or conservation returns no successful
partial cascade. Bounds and tolerances do not establish arbitrary conditioning
or physical model accuracy.

## Contracts and immediately runnable workflow

Worker `run_rlgc_line_cascade` accepts exactly `{'request': ...}`. Request
`spike/rlgc-line-cascade-request/v1` has exactly `contract`, `sections`,
`excitations`. Each ordered section has `id`, a positive-frequency parent
`line_request` and local `probes`. The external excitation array uses the
uniform field request's `frequency_hz`, `incident_left`, `incident_right`
complex `{real,imag}` representation in RMS sqrt(W).

Result `spike/rlgc-line-cascade-result/v1` retains `model_status`,
`production_qualified=false`, complete original `source_request`, canonical
SHA-256 `input_digest`, compatible external `network`, `sections` each containing
`id` and complete parent field `result`, per-frequency `points`, `diagnostics`
and `limitations`. Each point has frequency, global `power_balance` and ordered
`junctions` with adjacent section IDs and raw complex V/I/signed-power residuals.
Diagnostics retain sample/section count, maximum absolute global/interface
power residual and maximum connection condition number. Strict schemas are
registered; runtime also enforces cross-field/numerical conditions.

```powershell
.venv/Scripts/python.exe -m python.spike_core.cli --output build/my-cascade.json rlgc-cascade examples/rlgc_line_cascade/three-sections.request.json
.venv/Scripts/python.exe examples/rlgc_line_cascade/run_line.py
```

The original saved example supplies three different sections with coherent
external drives at three frequencies. It is a mathematical frequency-domain
example, not a broadband eye/TDR sweep or extracted PCB channel. Existing SI/PI
readiness checks remain separate and are rerun after integration.

## Verification and remaining physical scope

Independent references include a spatial exponential chain with direct boundary
solve, section-by-section quadrature, lossless interface power, identical-section
segmentation invariance, coherent both-end excitation, scaling, exact zero and
strict malformed/resource/conditioning/cancellation cases. Probe count never
sets the continuous loss integral. No independent measurement is supplied.

This is a supplied scalar series cascade with ideal electrical continuity.
There is no three-way branch, return change, connector, launch, via, bend/fringing
discontinuity or geometry/material extraction model. General dispersive
constitutive energy, broadband causality, DC/transient fields, thermal deposition
and temperature feedback remain separate. Knowledgeable human numerical review
before release is required. SI02 and whole PI/SI parity remain incomplete.
