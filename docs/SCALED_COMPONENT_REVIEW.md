# Scaled component placement review

`prepare_scaled_component_review` connects the bounded native-source placement
reference to the supervised STEP scale service. It verifies the original STEP
bytes, snapshots the retained design, bakes scale into a separate derived asset,
and proposes a proper-rigid board-local matrix. It does not mutate the source
model/design, register a derived model or apply a project placement.

```python
from python.spike_core.scaled_component_review import prepare_scaled_component_review

proposal = prepare_scaled_component_review(
    design, source_component_id, source_model_id, original_step_bytes,
    native_version="10.0.6",
    expected_design_digest=reviewed_design_digest,
)
asset = proposal["derived_asset"]
rigid_matrix = proposal["model_to_board_mm"]
```

This synchronous function belongs in a worker or command-line process. Optional
`freecad_executable` and `cancellation_event` are forwarded to the existing
[bounded native scale service](COMPONENT_STEP_SCALE.md). Source byte/digest,
ownership, retained declaration, physical stack and board-frame checks run before
native preprocessing. Review controls are limited to 8 MiB of JSON before
snapshot allocation; source STEP is limited to 16 MiB. If the live design baseline changes during the job, no
placement proposal is accepted. The snapshot prevents changing vector aliases
from affecting the in-flight computation.

The admitted nonuniform control is the original 2x3x4 mm STEP, scale (2,1,0.5),
model rotations (15,30,45) degrees and offset (1.25,-2.5,3) mm. The same native
reference envelope requires a 0.035/1.53/0.035 mm stack, footprint origin (20,10),
front/back sides and 37/90 degree footprint angles. Other inputs reject; the
existing [unit-scale review API](COMPONENT_PLACEMENT_REVIEW.md) remains restricted
to its original controls and still rejects nonuniform scale.

## Geometry and matrix separation

The derived geometry contains D=diag(2,1,0.5). Its local bounds are 4x3x2 mm,
while volume remains 24 mm3 because det(D)=1. The proposed matrix contains only
the measured model/footprint rotations, backside and board-datum conversion,
plus translation. Do not apply the source scale a second time. Scale does not
multiply the source offset, and model rotations do not rotate that offset twice.

Column-vector order is `board_datum * footprint * Rz(-rz) * Ry(-ry) * Rx(-rx)`.
Positive-depth SPIKE coordinates and the native 0.05 mm mounting clearance are
preserved. Every matrix is checked as proper rigid. Four actual derived/reimported
solid vertex sets transformed by these matrices match the independent retained
native [STEP reference](validation/parity/WF01-S04C3.md) at 1e-6 mm; orthogonality
and determinant +1 are checked at 1e-12 in the regression.

## Review and derived identity

The result is always `review_required`. `source_component_id` and
`source_model_id` identify the original owners; they are not a registered derived
model identity. Original/derived SHA-256 and scale/native facts are retained in
`derived_asset`. `derived_model_registration_required` is true. Automatic source
projection, material qualification and solver readiness remain false.

Retain the derived asset under a separately reviewed identity/digest before
building an explicit STEP handoff. Keep its source/scale relation and update
the retained design baseline through the existing project workflow. Registration
changes the design digest, so revalidate ownership and use the current digest
for the handoff; do not reuse a stale proposal digest as a commit authorization.
A proposal is neither approval nor an executable original-model binding.

## Verification and limits

Five checks cover pre-native and resource rejection, stale-during-job detection, cancellation
propagation and the four actual native bake/placement cases. Independent review
also compared retained native corners and confirmed that scale appears once.
Reproduce with installed FreeCAD available:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_scaled_component_review -v
.venv/Scripts/python.exe scripts/parity_scaled_review_gate.py --output build/scaled-review.json --log build/scaled-review.log --native-evidence build/scaled-review-native.json
```

Gate outputs must be new repository paths. Skips, failures, changed dependency
receipts/sources or native artifacts cannot support Done. The earlier unit-scale
stage is re-executed after the shared code change. This is a bounded Python
review workflow, not a new GUI/transport feature. General STEP models/stackups,
automatic placement, curved-scale fidelity and conditioned material evidence
remain open. Knowledgeable human numerical review before release remains required.
