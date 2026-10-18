# Bake-then-rigid component review proposals

Status: Accepted for bounded worker/CLI review proposals.

## Decision

`scaled_component_review.py` composes existing source-fact admission and native
derived STEP scaling. It snapshots a normalized design and verifies the original
reference asset before any native process starts. It returns a derived geometry
record and a separate rigid placement proposal, never an original-model binding
or a project mutation. Native cancellation/resource limits remain those of the
scale service. Changed post-job baselines reject the proposal.

The original unit-scale public review API is unchanged. Source/frame/stack
admission and rigid composition are shared, with separate measured-control
checks at each public API. Re-running the original stage refreshes its source
bindings after this refactor. No importer/canonical source transform is promoted.

## Independent derivation and acceptance

For x_local, positive scale D is baked into geometry once. The remaining matrix
is `P*B*Rz(-rz)*Ry(-ry)*Rx(-rx)`, with measured native mounting/offset translation.
P flips native Y/Z into source-board XY and positive depth, preserving handedness;
B is footprint Z rotation with backside X flip when appropriate. Source offsets
are acted on by B, not by D or the model rotation. This separation retains a
proper rotation with determinant +1 and prevents duplicate scale application.

The [native STEP reference](../validation/parity/WF01-S04C3.md) is black-box method
provenance. All derivation, code, fixtures and oracles are originally authored;
no external implementation was read/copied. Four actual derived/reimported
polyhedral bodies, positioned using returned matrices, match its eight-corner
sets. The earlier unit-scale eight-corner checks also remain passing. Orthogonal
matrix conditioning is one; geometric scaling retains its own previously
qualified tolerances and rejection limits rather than claiming mesh convergence.

## Scope and registration

Only the original nonuniform model control and referenced cube/stack/sides/two
footprint angles are admitted. Proposals remain review-required, carry original
owner IDs and require separate derived-model registration. No material law,
contact, physical placement approval or general source-model qualification is
inferred. Registration changes the design baseline; the explicit handoff must
use current ownership/digest and a reviewed matrix. See the
[workflow](../SCALED_COMPONENT_REVIEW.md) and [scale decision](0080-derived-component-step-scale.md).
