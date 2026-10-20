<!-- SPDX-License-Identifier: Apache-2.0 -->
# SI01-S01 finite supplied-line candidate and corner comparison

This experimental stage compares finite supplied candidates through the public
worker and CLI. Source-bound verification is required for stage promotion;
physical qualification and human release review remain separate.

Run `python examples/si_candidate_study/run_study.py`, or
`python -m python.spike_core.cli --quiet --output result.json si-candidate-study examples/si_candidate_study/candidates.request.json`.
The worker method is `run_si_candidate_study` with exactly one `request` parameter.
Wire schemas are `si-candidate-study-request-v1.schema.json` and its result partner.

The observable is channel-facing loaded voltage divided by the open-circuit
Thevenin source voltage, in V/V. The existing linear SI workflow solves each
explicit two-port scalar uniform RLGC line with supplied endpoint/package/passive
models. A candidate is an explicitly supplied design alternative; a corner is an
explicit deterministic model setting. There is no inferred tolerance distribution.
No temperature-dependent line material or thermal feedback is inferred.

Every declared candidate must have exactly one case for every declared corner.
Cases share an explicit uniform frequency grid including DC, with 3–1024 samples;
all simulated transfer samples are retained. There are at most 8 candidates,
8 corners, 32 total cases and 16 limits. Requests are bounded to 2 MiB and complete
results to 32 MiB. Cancellation is checked before preparation and before/after
each child solve; maximum cancellation latency includes one bounded child solve.
Streaming size checks bound cumulative retained request/grid/case bytes before
launching further cases; a final streaming check also covers assessment overhead.
The child that first exceeds the remaining budget can execute before rejection;
there is no prediction of a future child result's serialized size.

For each supplied closed frequency band, min_gain/max_gain constraints compare
the finite sampled extrema directly with an inclusive supplied bound. Both
extrema and the worst witness retain case, corner, frequency and complex voltage.
Margins are gain−bound for floors and bound−gain for ceilings. Binary64 comparisons
use no implicit slack: near-boundary differences must be interpreted at solver
precision, not as physical certification. Equal extrema choose lowest frequency
then lexical case ID. Case-array reordering does not change witness traversal.

Failed and partial child cases are retained, and incomplete coverage cannot pass.
Completed numerical solves can fail supplied limits while retaining completed
execution status. Invalid/nonfinite child output is rejected and recorded as a
failed case. Input and each supplied child request have canonical JSON SHA-256
digests; child results also retain their expanded models and native workflow
digests. A failed corner makes the aggregate assessment incomplete, even if other
candidates pass; feasible_candidate_ids only lists individually complete passes.

## Physics and independent verification

Foundation: D. H. Staelin, *Electromagnetics and Applications*, MIT OCW text,
chapter 8, sections 8.1.1–8.1.2, printed pp. 229–232, equations 8.1.1–8.1.16.
[Official text](https://ocw.mit.edu/courses/6-013-electromagnetics-and-applications-spring-2009/f52f07ed81b664331bee2fec67df7db6_MIT6_013S09_chap08.pdf).
These sections cover the telegrapher equations, traveling waves, characteristic
impedance, Thevenin loading and reflection. Full relevant sections reviewed
2026-10-19; no third-party implementation, figure or test data copied.

Independent derivation in project notation: Vin=A Vl+B Il, Iin=C Vl+D Il,
Il=Vl/RL and Vs=Vin+Rs Iin imply

    H = Vl/Vs = 1 / (A + B/RL + Rs C + Rs D/RL).

For a lossless line, A=D=cos(βl), B=jZ0 sin(βl), C=j sin(βl)/Z0,
Z0=√(L/C), β=2πf√(LC). At matched loading H=0.5 exp(−jβl).
At DC, including distributed series resistance, H=RL/(Rs+R'l+RL).
Tests compute these formulas without calling backend matrix/loading helpers.
Frozen oracle tolerances: DC absolute 2e−12, relative 2e−10; complex lossless
transfer absolute 2e−11, relative 2e−9. Reused backend conditioning and line regime
checks remain authoritative; this stage introduces no new PDE discretization.

The deterministic comparison cannot establish continuous-band bounds, measured
accuracy, statistical yield, eye/BER/protocol compliance, physical layout
constraints, geometry extraction or nonlinear driver behavior. Receiver-die
voltage after package networks is a different observable. SI01's topology editor,
general topology classes and reviewed native-layout constraint export remain
open. Independent physical measurement validation and knowledgeable human review
of numerical code are still required before production release.
