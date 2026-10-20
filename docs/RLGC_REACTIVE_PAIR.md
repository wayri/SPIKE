<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI02-S09: sampled reactive physical boundaries for a supplied coupled pair

Experimental development method, 20 October 2026. This stage extends the
[resistive boundary](RLGC_TERMINATED_PAIR.md) around the unchanged supplied
[symmetric even/odd line pair](RLGC_COUPLED_PAIR.md). Each named physical port
has an explicit positive series resistance R, ideal series inductance L, and
ideal node-to-reference shunt capacitance C. The Thevenin source is behind R/L;
the capacitor is at the line node. All four terminals must be supplied.

## Governing laws and independent derivation

Use RMS complex phasors with exp(j omega t). Port line current enters the line
at either end; distributed field current points left to right. For one port,
Zs = R + j omega L, Yc = j omega C, Is = Iline + Yc V, and
Vs = V + Zs Is. R is ohm, L henry, C farad, V volt and current ampere.
The line producer supplies b = S a with a common positive real reference Z0
and physical ordered ports, V = sqrt(Z0)(a+b), Iline = (a-b)/sqrt(Z0).
Substitution of the physical KCL/KVL boundary, independently of the line PDE,
gives Ys = 1/Zs, Yt = Ys+Yc and

```
Gamma = (1 - Z0 Yt)/(1 + Z0 Yt)
d = sqrt(Z0) Ys Vs/(1 + Z0 Yt)
[identity - diag(Gamma) S] a = d
```

A conditioned four-by-four direct solve closes the unchanged modal producer.
No matrix inverse, regularization, clipping, reference conversion, interpolation
or hidden ideal-port approximation is used. The supplied even/odd RLGC laws,
co-directed basis, exact shared positive frequency grids and S[receiver,source]
conventions retain their original contracts and limits.

Instantaneous ideal laws vL = L di/dt and iC = C dv/dt yield time-average stored
energies UL = L abs(Is)^2/2 and UC = C abs(V)^2/2 for RMS phasors. Independently,
Ss = Vs conj(Is), Sl = V conj(Iline), PR = R abs(Is)^2, so

```
Ss - Sl = PR + j omega (L abs(Is)^2 - C abs(V)^2)
         = PR + j 2 omega (UL - UC)
```

Signed source and line complex powers are VA, PR is heat W, mean stored energy
is J, and reactive exchange is var. Absorbing sources retain negative real
source work. Global real source work equals terminal resistor plus line
conductor and dielectric heat. Ideal reactive exchange contributes no heat.
A zero capacitor has zero current; source current otherwise differs from line
current. Each frequency is an independent steady scenario: do not sum sample
powers or use these outputs as a transient thermal history. Named terminals and
complete child source/digests/fields remain available for explicit future thermal
ownership and coupling; this method makes no heat deposition or contact mapping.

## Primary source and clean-room provenance

Reviewed 20 October 2026: D. H. Staelin, *Electromagnetics and Applications*,
MIT online text (2011), [chapter 8 official PDF](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
Actual full-text review covers section 8.1.4, printed pages 237-239 (reactive
Thevenin terminations), and section 8.3.1, equations 8.3.1-8.3.9, printed
pages 249-250 (complex telegrapher equations). These establish boundary and line
physics; the four-port Norton/wave closure, RMS storage identity, implementation
and verification here were independently authored in project notation. No claim
of reviewing other energy sections or obtaining independent experimental data.
No external code, figures, prose, meshes or datasets were copied or translated;
the reference is mathematical guidance, not imported implementation or rights.
Original SPIKE source/tests/examples/documentation are Apache-2.0. Existing
NumPy/SciPy dependencies and their separately recorded licenses are unchanged.

## Numerical analysis and admission

R ranges 1e-6..1e12 ohm, L 0..1e3 H, C 0..1 F. These are admission bounds,
not a claim of physical validity throughout the Cartesian product. Admit at
most 1024 independent positive samples and 32 line probes; input is at most
8 MiB and result at most 32 MiB with an early conservative estimate and actual
streamed size checks. Fixed ideal passive L/C, finite positive R and the prior
modal producer's validity assumptions are required. Singular, unrepresentable,
overflowing and underflowing arithmetic fails; no artificial minimum reactance.
Reject feedback condition above 1e8. Retain raw feedback residual <=1e-10;
per-port KVL uses 1e-9 scaled tolerance and complex-power balance 1e-10 scaled
tolerance. Global real power uses 1e-10 times the maximum of incident/source/heat
scales. Zero input uses exact zero observables. Cancellation is polled during
admission, line propagation, feedback, child binding and result assembly; callback
failure is a structured failure, never partial success. Child request/digest,
network, physical/modal fields and individual heat splits are independently
bound before accepting the wrapper result.

There is no time/mesh discretization in this new boundary closure and no frequency
interpolation: frequency refinement is not convergence of a broadband model.
Existing distributed quadrature and its gates remain unchanged. Numerical
conditioning and roundoff limits still apply to electrically long/stiff cases.

## Verification and validity

Frozen observable tolerances: voltage/current abs 2e-11 plus rel 2e-9;
heat/complex power abs 2e-12 plus rel 2e-9; mean energy abs 2e-20 J plus rel
2e-9. The numerical fixture directly builds a physical four-state spatial PDE
matrix from self/mutual R/L/G/C, applies physical endpoint equations, and uses
SciPy matrix exponentials to solve and sample fields without the production
wave transform, feedback or modal propagation. A separate lossless scalar ABCD
formula tests loaded transfer. Pure zero-L/C is compared with the unchanged
resistive stage. A large-storage case explicitly distinguishes J, var and W.
Zero/scaling, port ordering, conductor permutation, line reversal and an absorbing
source test signs and identities. Malformed data, conditioning, resources,
cancellation, callback failure and split-preserving child heat forgery must fail.
Actual worker, CLI, saved example, strict schemas and provenance are tested.

The source-bound stage receipt binds exact source hashes, test identities and
raw execution log; [validation record](validation/SI02_REACTIVE_PAIR_20261020.md)
records executed evidence and prior-stage replays. Independent agent review
supports numerical review but does not replace required knowledgeable human
review before release. No measurement correlation or full SI/PI parity is claimed.
General RLC topology, ideal open/short boundaries, nonlinear/frequency-dependent
or lossy reactive devices, broadband causal fitting, transient initialization,
geometry/material extraction, physical thermal allocation and original-board
qualification remain separate open stages.
