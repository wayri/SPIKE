# Derived STEP geometry with positive scale

`scale_component_step` creates a separate derived STEP asset by applying positive
axis scales about the source model origin. Geometry carries the scale; placement
matrices remain rigid. Source data, retained model records and projects are not
changed. The synchronous function belongs in a worker or command-line process,
not a desktop event handler.

```python
from python.spike_core.component_step_scale import scale_component_step

derived = scale_component_step(
    retained_step_bytes, [2.0, 1.0, 0.5],
    expected_sha256=retained_source_sha256,
)
geometry = derived["geometry"]  # Embedded STEP bytes and their derived SHA-256.
```

The expected digest must come from the retained/reviewed source baseline.
The returned record retains source SHA-256, applied scales, actual native and
reimported geometric facts, native version and the derived asset digest. Units
are mm after native STEP import/export. No source model URI is fetched.
Material/solver qualification stays false and review remains required.

For an [explicit component handoff](MCAD_EXPORT.md), register/retain the derived
model under an appropriate reviewed identity/digest and preserve its source/scale
provenance. The existing handoff still requires exact occurrence/design ownership
and a reviewed rigid matrix. A binding to a model whose digest identifies the
original unscaled asset remains rejected; do not overwrite a source digest to
bypass that guard. Do not apply scale again in the placement matrix. This helper
does not register assets, generate source placement, commit projects or infer
material laws, contacts or physical dimensions beyond the supplied CAD.

## Admission and failure behavior

The existing optional FreeCAD runtime runs a fixed owned script in an isolated
temporary directory. Only source STEP bytes and a bounded JSON scale request are
input. There is no caller-provided script, native output path or external URI.
The supervisor supports cancellation and enforces 90 seconds, 4 GiB memory,
16 MiB STEP input/output and bounded stdout/stderr/metadata. Factors must be
finite positive numbers in [0.001,1000], with axis ratio at most 1e6. This range
does not guarantee that every geometry is resolvable by the CAD kernel.

Exactly one valid closed solid is required. Sheets, multiple solids, mixed
solid/non-solid shapes, changed source digests, zero/negative/boolean/nonfinite
scales and unsuccessful native execution do not return an accepted asset.
Native geometry must pass determinant-scaled volume, positive-scaled bounds and
a fresh STEP reimport. At most 256 vertices are reported/compared; larger sets
are explicitly marked `omitted_over_limit`, retaining count and volume/bounds
checks without claiming a complete vertex equivalence witness.

Volume tolerance is relative 1e-8 with no absolute floor. Conservative OCC
optimal bounding boxes can include about 1e-7 mm padding even for planar source
faces. Bounds therefore use absolute 2e-6 mm or relative 1e-9 tolerance, while
reported scaled polyhedral vertices use strict absolute 1e-8 mm in the worker.
These are distinct observables. Neither conservative bounds nor kernel validity
alone establish correct curved geometry.

## Evidence and limitations

FreeCAD 1.1.3 probes pass six successful polyhedral cases and thirteen expected
rejections, including a translated box, triangular prism and explicit large
vertex omission. Three supervised original-cube scale cases compare actual
derived/reimported vertices to independent analytical corners; a fourth native
case rejects the curved conversion through the production caller.

An original cylinder (radius 2 mm, height 4 mm) has source volume 16*pi mm3.
The tested anisotropic conversion reports 50.698539286 mm3 instead of
50.265482457 mm3: a 0.8615% discrepancy. It is rejected. The cause is not resolved,
the volume tolerance was not widened, and general curved-solid scaling is not
qualified. Source/derived hashes, geometry and units are admission evidence,
not manufacturer, material or physics qualification.

Original fixtures, scripts and probe records are retained in
`benchmarks/parity-import/step-scale/`; no vendor geometry or implementation was
copied. All are SPIKE-owned Apache-2.0 material. FreeCAD/Open CASCADE remains a
separately installed dependency and is not redistributed by this stage.

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_component_step_scale -v
.venv/Scripts/python.exe scripts/parity_step_scale_gate.py --output build/scale-stage.json --log build/scale-stage.log --native-evidence build/scale-native.json
```

Run native checks with installed FreeCAD accessible. Gate outputs must be new
repository paths. The independent probe generator can run with FreeCAD's Python:
`benchmarks/parity-import/step-scale/probe_native.py`; it creates a fresh directory
under `build/step-scale-replay/`, including generated oversized rejection inputs.
Accepted [stage evidence](validation/parity/WF01-S04C5.json) binds current sources,
test execution, native artifacts and rejection evidence. Parent WF01-S04C remains
open for general placement and conditioned material qualification.
