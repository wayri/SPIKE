# ADR 0039: External volume engine admission

Status: Implemented, experimental; numerical release requires human review.

## Decision

Use the existing process-extension registry and declared workspace routes for
CalculiX thermal solves and Gmsh geometry. Reuse pure assembly field binding
before any external execution. Keep separately installed engine runtimes
outside SPIKE's Apache-2.0 distribution.

The dedicated CalculiX result contract retains executable/deck/output evidence,
source digests and actual temperatures. It is verified before host return and
again when reopening embedded field studies. It does not masquerade as an
internal numerical result with unsupported convergence or heat-balance fields.
Gmsh meshes retain complete source-owned topology and a normalized local datum;
viewport sampling never replaces the solver mesh.

## Consequences

Native solver and mesher preferences are independent. Declared geometry routes
can be available without solver compatibility. Arbitrary decks, shell commands,
user-selected interpreter paths and automatic visual-to-physics promotion are
excluded. Unsupported inputs, unavailable engines and stale bindings fail
explicitly. References, original analytical oracles, units and limitations are
recorded in CALCULIX_THERMAL.md and the Gmsh extension README.
