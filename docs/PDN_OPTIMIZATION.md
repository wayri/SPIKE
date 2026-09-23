# PDN Capacitor-Bank Optimization Contract

`schemas/pdn-optimization-v1.schema.json` defines
`spike/pdn-optimization/v1`. It is a solver-independent request/result
envelope for ranking explicit capacitor-bank configurations against a supplied
PDN source network.

## Boundary

An extractor or solver supplies the source impedance network and its exact
`model_status`. The optimizer consumes that network, explicit positive and
negative candidate terminals, a capacitor library, and stated objectives. It
does not infer a capacitor location from coordinates, fabricate mounting
parasitics, or improve the source solver's validity.

Each capacitor library entry declares capacitance, ESR, ESL, intrinsic mounting
R/L, count bounds, unit cost, voltage rating, and ripple-current rating. Each
candidate port declares both terminals and its port-specific mounting R/L.
Implementations combine those declared values only; their series/parallel
model, frequency grid handling, and any interpolation policy must be recorded
in the result provenance outside this envelope.

## Request

A request uses `record_type: request` and contains:

- `source_network`: source result identity, contract, exact model status,
  observation port, and frequency grid.
- `candidate_ports`: named, electrically explicit capacitor connections.
- `capacitor_library`: permitted part models and ratings.
- `objectives`: target-impedance curve plus target-violation, count, and cost
  weights. Optional total-count and cost limits constrain the search.

The schema limits both ports and library entries to 4,096. Runtime admission
must enforce the user-approved resource budget before enumerating combinations.

## Result And Validity

A result uses `record_type: result`. `source_model_status` is copied exactly
from the source network. Every recommendation also records its own inherited
`model_status`; it must never be stronger than its source. This semantic rule
is enforced by the optimizer/adapter because JSON Schema cannot compare two
dynamic enum values.

`search_scope` controls the permitted claim:

- `bounded` and `heuristic` results must use `claim: recommendation`.
- Only `exhaustive` results may use `claim: global_optimum`.

Even an exhaustive result is only optimal for the declared ports, library,
count bounds, objective weights, ratings, source network, and frequency grid.
It is not a general physical-placement or compliance claim.

## Solver Adapter Requirements

Adapters for sparseLizard, openEMS, PEEC, or other solvers must publish a
traceable source network before this contract is used. At minimum it needs a
driving-point observation port and the location-specific transfer/local
impedance information needed by the chosen loading model. The adapter must
preserve solver version, mesh, material assumptions, terminal definitions,
frequency grid, convergence, and all warnings in provenance.

For high-voltage or kiloamp designs, capacitor voltage/ripple ratings are only
screening constraints. Temperature rise, nonlinear materials, contact and
busbar resistance, current sharing, creepage/clearance, corona, and protection
coordination require separate validated models and may not be hidden by an
optimization recommendation.
