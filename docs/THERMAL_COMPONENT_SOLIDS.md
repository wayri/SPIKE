# Retained component STEP solids for thermal meshing

The experimental component promotion workflow makes an explicitly selected
component model a retained AssemblyIR physical part. That part can then be
meshed by the same bounded Gmsh OCC workflow as an enclosure or mechanical part.
It does not convert a display mesh into a closed CAD volume.

## Requirements and review

The retained board design must reference the exact model ID in the component's
`model_ids`. The authoritative project model index must contain that ID as a
STEP model with a `package:models/artifacts/...` URI and a matching SHA-256.
Contradictory design and project model references are rejected. File paths,
unretained external models, GLB/glTF and other decorative geometry are not
fallback solid sources. Missing STEP references remain explicit inventory
blockers; retain and associate the exact source model before promotion.

SpiDeR's component placement contains XY, rotation and side, but does not define
a complete mounting height and package datum. Every promotion therefore requires
a reviewed 4-by-4 component-to-board transform. Translation is in millimetres,
the matrix is row-major, and rotation must be proper rigid (no scale, shear or
reflection). Bottom-side orientation, mounting Z and model alignment must be
reviewed explicitly. A source-derived XY/rotation draft is not sufficient proof
of physical placement.

The world transform is:

`board_world * reviewed_component_to_board * retained_model_transform`

The component becomes a child of the retained board frame. The existing mesher
applies the model transform to STEP coordinates; the retained field handoff
applies component and board placement and converts millimetres to metres.
Copies of one board/model get distinct part and global source identities.

## Worker/API workflow

### Desktop steps

1. Save the assembly as a `.spike` project. Retain each component's closed STEP
   source in the project model index and associate its exact model ID with the
   component.
2. Open the assembly thermal mesh setup. Select the component and STEP model,
   enter reviewed conductivity and its provenance, and review the mounting
   transform, including bottom-side orientation and height. Promote the selected
   model, or use **Queue reviewed component** for each independently reviewed
   occurrence and **Retain reviewed component batch** to save them together.
   Each queued component retains its own STEP identity, transform and material;
   changing the opened manifest clears the queue. The batch is bounded to 100
   selections; joint meshing remains bounded to 64 source solids including board
   layers. Promotion updates the saved assembly and invalidates prior results.
3. Assign every retained physical part and board layer a material, then generate
   the Gmsh volume mesh. Inspect the actual occurrence geometry before using it.
4. Retain the intended thermal links with reviewed total resistance and contact
   area. In the contact editor, discover interfaces and apply selected ready
   links. Apply the edited thermal setup, including exterior boundary conditions.
5. In the volume electrothermal editor, copy the saved PI or SI circuit and
   reviewed volume setup. Explicitly rebind the circuit assembly after promotion.
   Declare a package thermal-only when its electrical device already exists in
   the board circuit. Map every resistor loss to occurrence/cell IDs and supply
   the temperature law and its valid range.
6. Choose **CalculiX external thermal**, prepare the coupled case, run, and save
   the admitted result. Inspect occurrence extrema, interior nodes, mesh edges
   and Kelvin/Celsius temperatures. A failed prepare or solve is a blocker;
   there is no silent internal-solver fallback.

`read_assembly_thermal_mesh_setup` now returns:

* `components`: board/design/component identity, reference, retained placement,
  referenced model eligibility and already promoted part IDs.
* `thermal_materials`: previously reviewed promotion material properties.
* `part_material_assignments`: retained promoted-part material IDs.

Call `promote_thermal_components_in_project` with exact saved project identity,
`expected_manifest_payload_sha256`, `materials` and `selections`. Each selection
contains `board_occurrence_id`, `component_id`, `model_id`, `material_id`,
`component_to_board_transform_mm` and `placement_reviewed: true`. Material rows
use the existing thermal mesh assignment format: explicit conductivity or a
symmetric positive conductivity tensor, ID and provenance. Every supplied
material must be used; reusing an existing ID with different properties fails.

The service validates retained STEP bytes against the manifest, checks project
freshness again before committing, preserves package members, records an audit
event and uses the normal assembly result invalidation/archive behavior.
It returns the new manifest and assembly, promoted parts, material assignments
and whether active results were invalidated. Repeated promotion of the same
board/component/model fails without modifying the package.

After promotion, include those part assignments and reviewed materials in
`run_assembly_thermal_mesh_in_project`. The part provenance binds the original
component, source design identity and indexed model reference. Changed source
component placement or changed model bytes/transforms block subsequent meshing
until the retained part is reviewed and replaced. Later explicit part movement
through assembly tools is allowed; its current retained frame is authoritative.

Implementation ownership:

* `assembly_thermal_components.py`: inventory, pure promotion and stale-source
  admission.
* `service_project_thermal_mesh.py`: manifest-bound package mutation and mesh
  service integration.
* `assembly_thermal_meshing.py`, `assembly_thermal_cad.py`: retained body jobs and
  closed STEP admission in the isolated OCC process.
* `schemas/thermal-component-promotion-v1.schema.json`: worker parameter shape.

## Evidence and remaining limits

See the [CalculiX full-chain verification record](validation/THERMAL_COMPONENT_CALCULIX_20261006.md)
for native circuit feedback, actual engine checks and remaining acceptance.

The original synthetic regression creates a one-cubic-millimetre STEP solid
through the admitted local Gmsh API, promotes it on two retained board copies,
then executes the actual bounded Gmsh process. It checks four generated bodies,
the independently known solid volumes, millimetre-to-metre conversion, separate
occurrence/source identities, model offsets and board/component placements.
No upstream example geometry or implementation was copied.

Run the focused suite with the project Python environment:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_thermal_component_promotion -v
```

The real OCC test requires the configured Windows CPython 3.11 runtime and
hash-admitted Gmsh 4.15.2 installation. It is skipped by other interpreters.
Pure tests cover manifest staleness, package-member retention, duplicate-board
identity, explicit material/placement admission and stale source withholding.

This bounded implementation still requires **one closed solid per STEP model**.
Compounds, open sheets and mixed display/solid STEP remain blocked rather than
being silently assigned one material or welded together. Promote separately
retained closed component models where needed. Mesh output, process time and
memory remain bounded by existing OCC limits. Overlapping retained bodies fail
the field handoff's geometry audit. Promotion creates no thermal contacts,
electrical models, heat sources or boundary conditions: those must be supplied
explicitly. This is
experimental geometry support, not production or measured thermal qualification.

## Using component volumes with existing board circuit losses

A package may receive heat from a resistor already represented in its board's
circuit. Set the multiboard circuit request's explicit `thermal_only_part_ids`
list to those promoted package part IDs. They remain required physical thermal
volumes and can receive normal occurrence/cell loss bindings, but have no second
passive `part_models` entry. A part cannot be both excluded and separately
modelled electrically.

Exclusion is admitted only for retained `component` parts with promotion
provenance, a valid owning board/design/model binding and the owning board's
parent frame. Every source-provenance digest is required. An excluded body must
not be an endpoint of any retained electrical bond. Ordinary mechanical parts
and enclosure current paths remain electrically explicit. The compiler reports
`excluded_thermal_part_ids`; an absent or empty input list preserves earlier
circuit behavior. This is an explicit modelling choice, never automatic loss
or circuit omission based on component names.

`tests/python/test_multiboard_volume_thermal_only_parts.py` verifies an actual native MNA and
tetra thermal solve where the existing board resistor heats a promoted package,
with unchanged total circuit dissipation and no duplicated device resistor.

## Conforming interfaces between generated occurrences

When at least two physical occurrences are generated, the mesher now places all
reviewed board-layer prisms and retained closed STEP solids in world millimetres
and performs one bounded OCC Boolean fragmentation and tetra mesh. Touching
faces acquire the same surface triangulation. Positive-volume overlap between
different occurrences is rejected from Boolean source ancestry before meshing;
no material priority can conceal an inter-part overlap.

The backend then partitions tetrahedra by their exact retained source owner,
inverse-transforms each body's coordinates to its occurrence-local frame, and
copies shared interface nodes into separate occurrence meshes. The shared field
handoff consequently has distinct temperature unknowns on each side. Thermal
contact still requires a retained link and explicit reviewed resistance. No
nearest-face matching, snapping, gap closure or implicit thermal weld is used.

`assembly_thermal_joint_mesh.py` owns request admission, occurrence splitting and
source/material preservation. The existing OCC worker supplies process bounds
and pinned-runtime admission. Joint generation permits at most 64 source solids
and 2048 total polygon vertices; per-output cell and vertex limits still apply,
including duplicated interface nodes. Larger assemblies fail explicitly rather
than falling back to independently meshed, nonconforming interfaces. One-body
generation retains its earlier meshing path. Meshes report
`meshing_mode: joint_conformal` and actual per-occurrence CAD/tetra volumes.

OCC Boolean tolerance can close a real small gap. Joint meshing therefore
captures each original CAD boundary **before** model and occurrence transforms
or fragmentation, applies the admitted rigid transforms to that evidence, and
checks every cross-occurrence shared triangle against both original finite
faces. Supported shared source faces are analytic planes bounded by a single
convex loop of straight edges. Every triangle vertex must satisfy all original
edge halfspaces and lie on the original plane. Curved, concave, holed or
unclassified shared source faces fail explicitly; separated solids with those
faces remain meshable. An infinite supporting plane or bounding box alone is
insufficient evidence of contact.

Plane and halfspace evaluation allow only floating-point roundoff:
`64 * machine_epsilon * max(1, absolute_coordinate_mm)`, capped at `1e-10 mm`.
Coordinates that need a larger allowance block interface admission. This bound
is below the contact matcher's `1e-12 m` coordinate tolerance; gaps below the
representation-roundoff allowance cannot be distinguished by this method.
The mesh records actual maximum projection error, allowance and checked triangle
count in `joint_interface_admission`. The actual Gmsh regressions reject
tolerance-closed positive gaps of `1e-8`, `1e-10` and `1e-12 mm`, preserve exact
touching source faces, and check rotated two-board interfaces. This gate does
not claim arbitrary CAD near-contact certification.

The original regression `tests/python/test_assembly_joint_thermal_mesh.py` runs
the actual pinned Gmsh process on a 2-by-2-by-1 mm board prism touching an equally
sized original STEP package. For conductivity 2 W/(m K), each slab has
`R = L/(k A) = 125 K/W`. With an explicitly retained 50 K/W interface and fixed
300/400 K outside faces, exact steady flow is `100/(125+50+125) = 1/3 W`; interface
temperatures are 341.6666667 K and 358.3333333 K. The generated matching faces
pass the autolink workflow, the internal solver satisfies those values within
1e-6 K, and the installed CalculiX solver satisfies them within 0.002 K (its
printed temperature precision). A separate real Gmsh run rejects overlapping
bodies; a 0.01 mm gap produces no contact proposal. These are bounded analytic
software tests, not arbitrary CAD robustness or production qualification.

## QuickTherm comparison

See [the working-tree comparison and proposed shared benchmark](QUICKTHERM_PACKAGE_COMPARISON.md)
for board-grid versus package-volume coverage and external validation limits.
