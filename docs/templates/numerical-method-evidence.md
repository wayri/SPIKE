<!-- SPDX-License-Identifier: Apache-2.0 -->
# Numerical method evidence: replace with bounded feature name

Template only; no implementation, execution or validation claim. Replace each
placeholder with actual evidence or an explicit unresolved gap before promotion.
Follow the [evidence policy](../NUMERICAL_METHOD_EVIDENCE.md) and
[clean-room policy](../RESEARCH_AND_CLEAN_ROOM_ENGINEERING.md).

## Claim and physical model

- Stage/method owner, current status, intended observable and supported envelope:
- Governing equations, constitutive/empirical laws and subject-matter assumptions:
- Units, tensor/shear/sign conventions, coordinate frames and relevant scales:
- Geometry/domain, initial/boundary/interface conditions and omitted physics:
- Law provenance, material ranges, uncertainty and extrapolation behavior:

## Source ledger

| Author/publisher; exact title | Year/revision; DOI/official URL | Reviewed equation/section/page; access extent/date | Source fact, SPIKE inference and applicability | Rights/status of use |
| --- | --- | --- | --- | --- |
| Record actual source | Record actual locator | Distinguish metadata/abstract/method/full text; leave unavailable sections unresolved | State a precise claim and limits | Foundation/design guidance/candidate/implemented lineage; do not invent historical adoption |

## Independent derivation and numerical method

- Derive strong/weak/discrete or compact equations in SPIKE notation:
- State spaces/operators/constraints/nullspaces and material history/state:
- Derive energy/work/conservation/dissipation and coupling transfer identities:
- State nonlinear tangents, solver scaling/conditioning and stopping criteria:
- State mesh/time/frequency/outer-domain controls and convergence assumptions:
- State resource, unsupported-input, stale-state and cancellation behavior:
- Explain independent implementation and any separate engine/model/data rights:

## Verification and validation plan versus executed evidence

| Case and independent reference | Observable/unit/tolerance set before execution | Refinement/invariants/failure controls | Executed source, input, output and log binding and actual result | Remaining applicability gap |
| --- | --- | --- | --- | --- |
| Record actual case; do not reuse tuned data as held-out validation | Record quantitative limits | Record meaningful controls | Distinguish planned/unrun from executed | Preserve unknowns |

Record physical measurements and uncertainty separately from synthetic/reference-
code comparisons. Record calibration split, regime coverage and model discrepancy.
Record hardware/precision and end-to-end cost at equal error for acceleration.
For research/learned models add maturity, OOD/abstention/fallback and training cost;
for adjoints add gradient verification and nonsmooth-region limits.

## Review and promotion

Record subject-matter and numerical review findings/extent; distinguish agent
review from required human release review. Record exact bounded acceptance met,
open family/release gaps and links updated in solver mathematics/references/status.
