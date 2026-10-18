# Component placement review drafts

The bounded Python helper `draft_kicad_component_placement` proposes a placement
for review using retained source footprint/model facts and the original native
STEP reference. It requires no native process and reads no model file or URI.
It does not change the design or apply a placement.

```python
from python.spike_core.component_placement_review import draft_kicad_component_placement
from python.spike_core.spider_v2_schema import content_digest

draft = draft_kicad_component_placement(
    design, component_id, model_id,
    native_version="10.0.6",
    expected_design_digest=content_digest(design),
    step_sha256=supplied_step_sha256,
)
# Review draft["model_to_board_mm"] against the actual mounting/asset evidence.
# Explicit STEP handoff still needs occurrence ownership, geometry and a review reference.
```

`design` is the retained normalized design, not a native parser object. Obtain
the expected digest from the baseline that was reviewed; the example computes
it locally for a current immutable snapshot. The version argument is a supplied
declaration, not a live KiCad-version discovery or authentication.

The result retains component/model IDs, exact design and supplied STEP digests,
native-reference identity, observed mounting clearance and a row-major 4x4
board-local proper-rigid matrix in mm. Its status is always `review_required`.
Copying a matrix after review into the [explicit STEP handoff](MCAD_EXPORT.md)
is a separate action; the existing handoff still validates baseline, ownership,
STEP bytes/digest and occurrence completeness. A draft does not certify the
publisher or actual bytes corresponding to a supplied digest.

## Limits and recovery

Only the original 2x3x4 mm STEP digest, 0.035/1.53/0.035 mm stack, footprint
(20,10) mm, 37/90 degree footprint rotations, front/back and two unit-scale model
controls are admitted. Missing native footprint origin, contradictory source
facts, changed baseline, unsupported version/STEP/stack and scale/rotation
outside that cohort produce `PLACEMENT_*` errors. Use an explicit reviewed
placement or establish additional native evidence; do not remove these gates.

The source footprint origin is authoritative for this draft. Canonical component
position can be a pad centroid and is not a substitute. Top-depth coordinates
begin at the full stack top. The observed native 0.05 mm component clearance is
retained; it does not establish physical separation/contact suitability.
Materials, thermal contact, automatic placement, GUI availability and general
source-model qualification are outside this helper's scope.

## Verification

Six tests compare eight draft matrices against all observed STEP corners,
check origin-versus-centroid behavior, reject stale/unsupported/malformed source
facts, and exercise the existing partial explicit STEP handoff. Reproduce:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_component_placement_review -v
.venv/Scripts/python.exe scripts/parity_component_review_gate.py --output build/component-review.json --log build/component-review.log
```

Gate outputs must be new paths. Failed/skipped tests and changed sources/native
receipts/logs cannot support Done. See [the decision and derivation](adr/0079-native-reference-placement-review-drafts.md).
