<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR0113: supplied symmetric coupled pair through scalar modal solvers

Status: accepted for experimental development, 20October2026.

General conductor coupling needs controlled steps beyond independent scalar
lines. A uniform symmetric pair admits a fixed orthogonal even/odd basis;
the established scalar network/field solvers can propagate each mode without
an arbitrary matrix eigensolver, new numerical dependency or new PDE kernel.

Add a versioned worker/CLI request with two supplied scalar modal line models,
four physical incident waves and common probes. Preserve the same real port
reference, exact grids and full child provenance. Compose physical S/V/I and
signed power orthogonally; retain storage and dissipative losses at pair/modal
level. Thermal consumers must not sum both representations or invent unique
conductor ownership for mutual terms.

Independent physical-coordinate matrix-exponential and loss-quadrature oracles
verify the composition. General asymmetric/noncommuting models, geometry
extraction, radiation, thermal mapping and physical qualification remain open.
See [derivation, primary references and limits](../RLGC_COUPLED_PAIR.md).
