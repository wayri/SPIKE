# ADR 0001: Normalized DesignIR

- Status: Accepted
- Date: 2026-08-09

## Context

SPIKE must analyze designs from KiCad and future standards/vendor sources while
supporting desktop, CLI, reports, tests, and optional remote execution. Direct
use of an EDA parser model in solvers or UI would couple every feature to that
source and make project persistence unstable.

## Decision

All design sources normalize into versioned, JSON-compatible `DesignIR` before
analysis. `AnalysisSpec` and `AnalysisResult` are likewise source and UI
independent. Units, coordinate rules, import issues, and provenance cross the
boundary explicitly.

## Consequences

- Importers absorb source differences and fidelity gaps.
- Solvers and reports work without an EDA installation.
- Project packages can preserve reproducible analysis context.
- The contract needs migrations when semantics change.
- Some current entity dictionaries are weakly typed and should become narrower
  versioned schemas without breaking `spike/v1` consumers.

## Rejected alternatives

- KiCad parser objects as the shared model: prevents EDA neutrality.
- UI-specific board state as the shared model: prevents CLI/cloud reuse.
- A different model per solver: duplicates import logic and breaks comparison.
