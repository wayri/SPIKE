# Native-reference component placement review drafts

Status: Accepted for bounded inert Python review drafts.

## Decision

`component_placement_review.py` produces an explicit board-local matrix proposal
from retained normalized source facts within the WF01-S04C3 native reference
envelope. It does not parse EDA files, open model URIs, alter designs, promote
materials or commit a placement. Existing importer and explicit mechanical STEP
handoff responsibilities are unchanged. The output's
`spike/component-placement-review/v1` contract is an internal Python review
record, not a new worker/transport schema or a GUI capability claim.

The caller supplies the exact expected retained-design digest, declared native
version and supplied STEP digest. Source component/model ownership, unapplied
model facts, physical stack, native footprint origin, side and angle must agree.
Canonical component position is not used: it can be a pad centroid. Unsupported
cases fail with a `PLACEMENT_*` ValueError and require the existing explicit
placement workflow or additional independent native qualification.

## Envelope and derivation

The only admitted STEP is the original 2x3x4 mm cuboid identified by its recorded
SHA-256. The stack is 0.035/1.53/0.035 mm; footprint origin is (20,10) mm;
orientations are 37/90 degrees on either side. Only the two measured unit-scale
controls (identity or 90-degree model Z rotation with offset (-1,0,4)) are
admitted. Nonuniform scale must not enter the existing rigid-transform contract.
Other geometry/angles/versions/stackups are deliberately unqualified.

The independently authored helper uses column vectors: native footprint Z
rotation, backside X flip, negative model Z rotation, then native-to-board
Y/Z axis flips and top-depth translation. The [native STEP reference](../validation/parity/WF01-S04C3.md)
is the black-box method/source evidence. Its copper datum maps native Z to
`1.565-Z`. Native mounting elevations 1.615/-0.085 retain the observed 0.05 mm
clearance. Orthogonal transforms have no scale conditioning amplification;
tests compare all eight transformed corners to observed solids at 1e-6 mm.
Geometry refinement is not involved in this exact rigid cuboid transform.
No external implementation, derivation text or fixture was copied.

## Review and application

Every draft stays `review_required`; `source_projection_enabled`, `solver_ready`
and `material_qualified` remain false. This status is informative, not an
authorization token. A caller may copy a reviewed matrix into the existing
explicit `component_models` handoff with its occurrence ownership, actual STEP
bytes, baseline digest and review reference. The handoff independently validates
those inputs. A partial handoff retains geometry omissions for other models.

The caller must review the actual mounting datum, source asset and exporter
clearance. The helper does not infer thermal contact or translate a native
clearance into a physical contact law. Knowledgeable human numerical review
before release remains required by CONTRIBUTING.md.
