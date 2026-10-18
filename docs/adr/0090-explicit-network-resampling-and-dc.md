# ADR 0090: Explicit sampled network resampling and DC

Status: accepted for bounded experimental development; release qualification open.

## Context

Network composition and time-domain preparation need compatible grids.
Silently changing grids or inventing DC data hides modeling assumptions and
can make unsupported causality claims appear credible.

## Decision

Add a versioned Python worker transformation for explicit complex Cartesian
linear resampling within a declared support range. DC is either already in
the source or supplied explicitly as a separate real matrix. Preserve source
identity, per-target support weights and active/nonreciprocal data. Do not
change existing workflow admission or imply causal fitting.

## Consequences

Users can audit a derived common grid and its approximation assumptions.
Independent affine and delayed-line refinement tests bound demonstrated
behavior. Automatic causality, extrapolation and fitted macromodels retain
separate acceptance stages. No dependency or language is added.
