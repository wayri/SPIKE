# Positive scale baked into derived STEP geometry

Status: Accepted for bounded derived-asset preprocessing.

## Decision and ownership

The Python `component_step_scale.py` service checks retained source bytes/digest
and explicit scales, invokes the existing bounded optional CAD-process adapter,
and returns embedded derived STEP geometry with native provenance. The fixed
`freecad_scale_step.py` worker owns native BREP transformation and fresh STEP
reimport. Neither changes imported source vectors nor scales placement frames.
No new engine dependency, transport endpoint or GUI workflow is introduced.
The result is an internal Python asset record, not an authorization token.

New geometry has its own digest and source/scale relation. Existing model and
explicit-handoff ownership/digest guards remain unchanged. Asset registration,
source placement review and saving a project remain separate explicit steps.
Material and solver qualification flags remain false.

## Independent derivation and evidence

For positive diagonal D, local geometry maps as x'=D*x. The Jacobian determinant
is sx*sy*sz, so closed-solid volume must satisfy V'=det(D)*V. Positive factors
preserve the ordering of each coordinate's extrema; scaled bounds are original
endpoints multiplied by their axis factor. Vertex witnesses check coordinates
and uniqueness separately; a determinant-one scale can change shape without
changing volume. All fixtures, code and arithmetic are independently authored.
The native observations and [workflow evidence](../COMPONENT_STEP_SCALE.md)
provide method provenance; no external implementation/tutorial data was read
or copied.

Matrix conditioning is bounded by max(scale)/min(scale)<=1e6, but native feature
size and CAD tolerance can still invalidate a request. Volume requires relative
1e-8 accuracy; bounding boxes have an independently observed kernel-padding
envelope, separate from strict polyhedral vertex coordinates. Exact geometric
preprocessing uses native/reimport witnesses rather than a mesh-refinement claim.
Topology validity and a small bound discrepancy do not certify general curved
geometry. The observed cylinder determinant failure remains rejected.

## Limits and release status

The validated native subset is polyhedral positive-scale preprocessing with
bounded vertex witnesses and declared omissions. One valid closed solid is
required; mirrors, degenerate scales, sheets/compound bodies and failed native
or roundtrip invariants reject. Inputs/outputs and process time/memory are bounded.
This does not establish general curved-solid fidelity, meshing quality, real
package material applicability or simulation prediction accuracy. Knowledgeable
human review before numerical code release remains required.
