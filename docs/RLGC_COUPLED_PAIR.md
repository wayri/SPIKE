<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied symmetric coupled RLGC pair

SI02-S07 composes the unchanged scalar sampled-network and driven-field solvers
into a supplied uniform symmetric pair. It returns four-port scattering,
coherent conductor voltage/current and signed transport, pair-level storage and
conductor/dielectric loss, and each complete child result with input provenance.
This is experimental supplied circuit physics, not geometric extraction.

Run `python examples/rlgc_coupled_pair/run_pair.py`, or
`python -m python.spike_core.cli --quiet --output pair.json rlgc-coupled-pair examples/rlgc_coupled_pair/symmetric-pair.request.json`.
The worker method `run_rlgc_coupled_pair` accepts exactly one `request` parameter.
Registered request/result contracts are `spike/rlgc-coupled-pair-{request,result}/v1`.

## Governing model and provenance

The supplied even and odd scalar RLGC models share positive length, real port
reference, strictly positive ordered frequencies and common probes. L/C are
constant and positive; R/G samples are nonnegative. For the stated co-directed
pair convention, Le≥Lo, Ce≤Co and Ge≤Go enforce the intended mutual signs.
The resulting symmetric R/G matrices are positive semidefinite and L/C positive
definite. Constitutive samples are assumptions, with no inferred substrate,
material temperature law, skin effect, return path or geometry ownership.

Foundation: Michael Steer, *Microwave and RF Design II: Transmission Lines*,
author-attributed online text, [section5.3](https://eng.libretexts.org/Bookshelves/Electrical_Engineering/Electronics/Microwave_and_RF_Design_II_-_Transmission_Lines_(Steer)/05:_Coupled_Lines_and_Applications/5.03:_Coupled_Transmission_Line_Theory)
equations1–10,18–23 and
[section5.5](https://eng.libretexts.org/Bookshelves/Electrical_Engineering/Electronics/Microwave_and_RF_Design_II_-_Transmission_Lines_(Steer)/05:_Coupled_Lines_and_Applications/5.05:_Symmetric_Coupled_Transmission_Lines)
equations1–20. Relevant full mathematical text reviewed20October2026, online
section5.3 revision22May2022. These establish lossless quasi-TEM matrix and
symmetric even/odd foundations. Lossy composition and normalization below are
independently derived; scalar distributed-loss provenance remains in
[the unchanged field method](RLGC_LINE_FIELDS.md). No external implementation,
example data, figure or prose is copied; source licenses do not supply code rights.

## Original derivation, signs and units

Define Q=1/√2[[1,1],[1,−1]], V=Q Vm, I=Q Im. This power-normalized convention
differs from half-sum electrical common/differential voltage conventions.
For each A in {R,L,G,C}, A=Q diag(Ae,Ao) Qᵀ, hence self=(Ae+Ao)/2 and
mutual=(Ae−Ao)/2. With exp(+jωt) phasors:

    dV/dx = −(R+jωL)I,     dI/dx = −(G+jωC)V.

QᵀQ=identity preserves Vᵀconj(I), IᴴRI, VᴴGV and L/C energy forms.
Each modal child receives transformed incident waves; physical outgoing waves
are reconstructed with the same orthogonal map. Modal order is e-left,e-right,
o-left,o-right. Physical port order is first-left,second-left,first-right,second-right.
With the common real Zref, V=√Zref(a+b), I_into=(a−b)/√Zref. All phasors are RMS;
incident waves have units √W, conductor current points left-to-right internally,
and right boundary inward current has the opposite sign.

Pair transported power is Re(Vᵀconj(I)); conductor contributions can be signed.
Pair time-average circuit storage is VᴴCV/2 and IᴴLI/2 in J/m.
Conductor/dielectric loss densities are IᴴRI and VᴴGV in W/m, equal to sums of
modal densities. Scalar children integrate these losses analytically over length;
probing does not discretize or allocate integrated heat. Total input power equals
that distributed loss, with retained raw terminal/wave residuals. Mutual terms
have no unique per-conductor thermal owner: pair loss and modal loss are two
views of the same heat and must never be summed together.

## Numerical analysis and verification boundary

An orthogonal map has condition1; no coupled matrix eigenvector search or new
propagation kernel is introduced. Child propagation and condition limits remain
authoritative, including350nepers/1e6radians and conditioned scalar boundary
solves. Four-port passivity/reciprocity tolerances are1e−9/1e−10. Raw power
residuals must be≤1e−10 times the largest incident/input/loss scale; exact zero
uses zero tolerance. No clipping, redistribution or hidden regularization occurs.

At most1024samples and32probes are admitted. The original JSON is bounded to8MiB;
an aggregate preflight estimate rejects oversized response work before child
solves. Streaming child-retention and final-response checks enforce32MiB.
Cancellation is checked before preparation, through both scalar solves and
between physical samples/probes. Failures return no partial coupled result.

The independent test oracle builds physical self/mutual matrices without using
production basis or scalar helpers and solves a4×4 spatial matrix exponential
with physical four-port boundary equations. S and V/I tolerances were fixed
before implementation at2e−11absolute+2e−9relative. Independent physical quadratic
storage/loss checks and32/64point Gauss quadrature use2e−12absolute+2e−9relative.
Units are respectively V/A, J/m and W/m/W. These are verification tolerances,
not measurement uncertainty or continuous-band bounds.

General asymmetric/noncommuting multiconductor matrices, bends/vias/return
discontinuities, field geometry, DC, time-domain/causal material models, thermal
deposition/feedback and measured accuracy remain open. No physical measurements
or learned models are used. Knowledgeable human numerical review remains
required before production release.
