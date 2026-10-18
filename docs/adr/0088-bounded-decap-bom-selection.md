# ADR 0088: Bounded supplied decap BOM selection

Status: accepted for bounded experimental development; release qualification open.

## Context

Operating-corner evaluation alone does not choose a population under inventory
and cost limits. An unconstrained best-impedance claim would hide rejected
populations and depend on undeclared parts and locations.

## Decision

Enumerate a bounded explicit discrete domain in a Python application service,
composing PI03-S01 without duplicating circuit stamps. Admit every part and
reserve aggregate numerical work before solving. Retain constraint rejections
and evaluated target failures. Use deterministic documented feasible and
infeasible ranking, and preserve the selected full corner result.

## Consequences

Selection is auditable and exact within the declared finite domain. The
service remains experimental and uses no additional dependency or language.
Physical location extraction, automatic material models, catalog/BOM import
and hardware correlation require their own acceptance stages.
