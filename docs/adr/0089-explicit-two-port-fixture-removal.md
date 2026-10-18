# ADR 0089: Explicit sampled two-port fixture removal

Status: accepted for bounded experimental development; release qualification open.

## Context

Measured cascades include fixture response. Removing supplied fixtures needs
explicit orientation, reference impedance, frequency correspondence and
conditioning; an unqualified inverse can amplify errors or change identity.

## Decision

Use dimensionless real-reference wave-chain linear solves in a Python module
behind versioned worker contracts. Require exact grids and oriented port
names, reject ill-conditioned conversions, and preserve source snapshots and
diagnostics. Do not repair active data or infer calibration/causality.

## Consequences

Two supplied cascaded fixtures can be removed with independent wave-connection
acceptance evidence. Automatic calibration, uncertainty qualification and
multiport fixture removal retain separate stages. No dependency or new
implementation language is introduced.
