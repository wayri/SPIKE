# ADR 0087: Supplied decap operating corners

Status: accepted for bounded experimental development; release qualification open.

## Context

PI03 requires effective capacitor behavior across bias, temperature and
tolerance. A nominal-value comparison can miss target failures. SPIKE already
has a passive series-RLC decap stamp and multiport PDN analysis; duplicating
those equations would create inconsistent numerical behavior.

## Decision

Compose the existing Python PDN evaluator behind versioned worker contracts.
Require explicit complete corner tables and per-port impedance targets. Bias
and temperature identify supplied data, without an inferred constitutive law.
Preserve generated networks, source identity, failed targets and experimental
status. Bound the aggregate study and return no partial numerical success.

## Consequences

Users can audit supplied operating corners through the script workspace and
worker with independent scalar and multiport regression evidence. Automatic
catalog models, geometry extraction, optimization and measured qualification
retain separate gates. No dependency or implementation language is added.
