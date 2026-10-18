# BOM-constrained supplied decap selection

PI03-S02 searches an explicit finite set of capacitor parts and connection
sites. It composes the [operating-corner workflow](PDN_DECAP_CORNERS.md)
and its existing series-RLC PDN solver. Results are experimental development
evidence; physical extraction, automatic catalog models and measured
qualification remain open.

## Request and workflow

Use `run_pdn_decap_selection(request)` from
`python.spike_core.pdn_decap_selection`, or the worker method of the same name
with `params: {request: ...}`. The desktop script workspace can invoke the API.
The `spike/pdn-decap-selection-request/v1` contract supplies:

- `base_request`, `corners`, `target_impedance_ohm_by_port`: the same explicit
  passive network, operating conditions and sampled targets used by PI03-S01.
- `sites`: unique IDs, positive/negative network nodes and one to four part
  options. Each option has an ID, `part_id`, integer `unit_cost_minor`, source
  provenance and a complete supplied C/ESR/ESL operating-corner table.
- `inventory`: exactly the used part IDs and their integer `max_quantity`.
- `budget_minor` and `max_capacitors`: hard total cost and population limits.

Money uses one caller-chosen currency's minor unit throughout, with no currency
conversion or fractional arithmetic. Counts and costs reject booleans.
The same part ID must carry identical physical values, cost and provenance
wherever offered. Separate IDs represent physically different variants.
Bias and temperature are labels for supplied values; no derating is inferred.

The search considers omitting a site or choosing exactly one option there.
It excludes the all-empty population. A base-only study can be run directly
with the PDN evaluator. Every nonempty population is enumerated in declared
site/option order; omitted sites precede options. No heuristic pruning drops
an electrically poor candidate. Constraint-rejected populations retain their
selection, counts, costs and reasons, with null electrical outcomes.

## Selection and numerical evidence

All constraint-admissible populations execute every declared corner. Among
populations meeting every sampled driving-point target, ranking is least cost,
then least worst target ratio, then fewest capacitors, then enumeration order.
If none meet the targets, ranking is least worst target ratio, then cost,
then capacitor count, then order; `meets_target` remains false. The winner's
full generated networks, provenance and corner results are returned alongside
every population summary. A search with no constraint-admissible population
returns a structured error. Numerical failure or cancellation
also returns no successful partial search.

For each sample the unchanged core solves the supplied network with each
capacitor impedance `ESR + j*w*ESL + 1/(j*w*C)`. Site-specific behavior comes
from the declared network connections. Exhaustive enumeration establishes the
stated ranking only over those finite supplied populations and samples.
It cannot establish an optimum over arbitrary board geometry, missing parts,
unsampled resonances or transfer/transient targets.

Original fixtures compare every evaluated scalar population with independent
parallel-admittance equations and independently enumerate feasible rankings.
Multiport checks retain supplied return-path effects. Constraint, identity,
failure and cancellation cases are exercised through Python and the actual
worker with versioned schemas. The derivation, code and fixtures are original
SPIKE work, using no external implementation or catalog data. The existing
equilibrated condition limit of 1e12 and backward-error limit of 1e-10 remain
unchanged. There is no iterative optimizer or new convergence criterion.

## Limits and recovery

At most eight sites, four options per site, sixteen corners and 256 nonempty
populations are admitted. Request/response bounds are 8/16 MiB; aggregate
numerical work is bounded across every admissible population before solving.
Reduce or split a rejected search explicitly. Every option is admitted even
when a budget would exclude it, so invalid data cannot hide behind a constraint.
Singular networks, invalid coverage or inconsistent part identities require
correcting the request. Original inputs remain unchanged.

PI03 remains in progress. This stage introduces no dedicated desktop editor,
automatic site extraction, catalog ingestion, procurement action or measured
signoff. Knowledgeable numerical review is required before release.
See the [request schema](../schemas/pdn-decap-selection-request-v1.schema.json),
[result schema](../schemas/pdn-decap-selection-result-v1.schema.json), and
[source-bound stage evidence](validation/parity/PI03-S02.json).

## Development acceptance

On 2026-10-18 all ten source-bound stage checks passed with zero skips. All
eight earlier PI/SI stage suites were rerun and their canonical receipts
refreshed. Combined regressions passed 153 tests with zero skips (14.407 s).
Architecture, eight changed documentation files and the 61-family backlog
checks passed. The full release suite was not rerun for this bounded stage;
broader qualification and knowledgeable human numerical review remain open.
