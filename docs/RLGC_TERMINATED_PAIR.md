<!-- SPDX-License-Identifier: Apache-2.0 -->
# Physical source and load boundaries for a supplied coupled pair

SI02-S08 closes the sampled four-port coupled-line response with explicit
physical-port resistive Thevenin sources and loads. The unchanged pair solver
then computes conductor fields for the solved incident waves. Results preserve
the original inputs, full coupled/modal children, terminal voltages/currents,
signed source powers, resistor heat and distributed line heat.

Run `python examples/rlgc_terminated_pair/run_pair.py`, or
`python -m python.spike_core.cli --quiet --output loaded.json rlgc-terminated-pair examples/rlgc_terminated_pair/unbalanced.request.json`.
The worker method is `run_rlgc_terminated_pair` with exactly one `request`.
Registered contracts are `spike/rlgc-terminated-pair-{request,result}/v1`.

## Supplied model, physical signs and primary reference

The pair model contains conductor IDs, modal models and probes with the
[unchanged S07 limits](RLGC_COUPLED_PAIR.md). Every physical port has exactly
one named resistance in 1e−6..1e12 Ω. Every positive frequency has four explicit
RMS source phasors. Zero voltage defines a passive resistive load. Missing ports,
zero/infinite/negative or reactive resistances, nonlinear drivers and inferred
source waveforms are unsupported. Termination record order is arbitrary; port
order remains first-left, second-left, first-right, second-right.

Primary foundation: D. H. Staelin, *Electromagnetics and Applications*, MIT OCW
online text (2011), [chapter 8](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf),
sections 8.1.1–8.1.2, printed pp. 229–232, equations 8.1.1–8.1.16. Relevant full
text reviewed on 20 October 2026 for Thevenin excitation and resistive reflection.
The feedback and energy derivation below is independently authored. Lossy and
coupled constitutive foundations remain in the S04/S07 method records. No
external code, figure, example data or prose was copied.

## Original feedback and energy derivation

With exp(+jωt), RMS power waves and current positive into the line:

    V = sqrt(Zref)*(a+b),   I = (a-b)/sqrt(Zref),   V+Rt*I = Vs.
    a = Gamma*b+d,         Gamma = (Rt-Zref)/(Rt+Zref),
    d = sqrt(Zref)*Vs/(Rt+Zref),   (identity-diag(Gamma)*S)*a = d.

Each row of S maps incident to outgoing waves in the same real reference.
Normalize R and Zref by max(R,Zref) before forming ratios. The implementation
solves the feedback matrix directly, then passes actual coherent incident waves
to the unchanged pair solver. Unbalanced physical loads generally couple both
modal excitations even when the propagation basis itself is fixed.

For each terminal, multiplying V+Rt I=Vs by conj(I) and taking its real part gives

    P_source = Re(Vs*conj(I)) = Re(V*conj(I)) + Rt*|I|^2.

Summing ports and using the existing line conservation identity yields signed
source work = terminal-resistor heat + line-conductor heat + line-dielectric heat.
An ideal source can absorb power, so its signed work is never clipped. Resistor
heat is nonnegative, labeled by explicit terminal ID, and remains separate from
the pair/modal representations of the same distributed line heat.

All powers are W per independent sampled steady-frequency scenario. No implicit
sum over scenarios, multitone waveform reconstruction, frequency integration or
conversion to a transient thermal load occurs. Terminal IDs identify lumped heat,
not physical contacts or cells. A thermal consumer must select an operating case
and provide physical ownership and mapping; it must not add nested modal loss to
the already-counted pair loss.

## Numerical analysis, provenance and rejection

The feedback condition limit is 1e8; residual norm must be at most 1e−10 times
`norm(M)*norm(a)+norm(d)`. KVL and reconstructed child boundary comparisons use
relative 1e−9. Source/line heat residuals use 1e−10 times the largest incident,
absolute source-work or dissipation scale. Exact zero uses zero tolerance.
No inverse, artificial series resistor, clipping or residual redistribution repairs
a failed system. Scalar propagation, underflow/overflow and pair validity checks
remain authoritative; these are sampled checks, not broadband causality proof.

Child contracts, canonical source requests/digests, grids, port/probe identities
and network matrices are bound. Physical boundary/interior fields, signed powers,
storage densities and conductor/dielectric heat are checked against the retained
modal constituents. Checking only total heat would allow a false loss split and
is explicitly insufficient. Verification trusts the source-bound scalar producers;
it does not certify arbitrary external forged models by inspection alone.

Limits are four ports, 1024 frequency samples, 32 probes, 8 MiB input and 32 MiB
output. Aggregate work/size admission occurs before solves, with streaming child
retention/final size checks. Cancellation reaches preparation, bare propagation,
feedback, driven fields and output validation. No partial successful study is
returned on admission, conditioning, cancellation or numerical failure.

## Independent verification and remaining limits

The independent oracle solves physical four-state spatial equations directly:
`z(right)=exp(M*length)z(left)`, with left `V+R I=Vs` and right `V-R I=Vs`.
It uses neither production wave conversion nor the feedback matrix. Frozen V/I
tolerances are 2e−11 absolute plus 2e−9 relative. Physical quadratic loss and
64-point length quadrature use 2e−12 absolute plus 2e−9 relative in W.
Matched-line divider/phase, source absorption, zero/scaling, reordered records,
conductor permutation/reversal and forged-result controls are separate checks.

General asymmetric geometry extraction, physical return discontinuities,
reactive/package/nonlinear loads, DC/transient behavior, causal material laws,
thermal deposition/feedback and measured accuracy remain open. This experimental
stage does not qualify EBrake, Marble, the complete SI02 family or a release.
Knowledgeable human numerical review remains required before release.

## 21 October 2026 boundary cancellation integrity correction

Physical endpoint reconstruction comparisons retain the 1e-9 relative criterion
with an additional 64*float64.eps local wave-operand allowance, solely for
near-zero boundary quantities. Modal-network/interior comparisons keep zero
absolute floor; physical values, heat/power/KVL and board gates are unchanged.
[Derivation, exact Higham source review, counterexample and limits](RLGC_LOADED_STAR.md)
record this correction. Factor 64 is a tested implementation allowance, not a
universal forward-error or near-zero relative-accuracy guarantee. Current source
bindings require real stage reexecution; historical receipts are preserved.
