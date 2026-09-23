# FreeCAD collaboration

Status: source implementation, companion workbench 0.2.0, 2026-09-07.
The existing installed SPIKE executable is not rebuilt by this source change.

## Working assembly feedback

In SPIKE open **MCAD assembly > Board instances and harnesses > FreeCAD
collaboration**. Save the project and pending assembly edits, then choose
**Export FreeCAD session**. The JSON contains a project/assembly revision binding,
stable occurrence IDs, parent-local placements, supported geometry and an
explicit omissions list. Repeated board designs remain separate occurrences.

In the SPIKE FreeCAD workbench choose **Open SPIKE Collaboration Session**.
Move or rotate the occurrence containers, or change their labels. Their geometry
children remain in board/part-local coordinates. FreeCAD's placement editor and
normal selection tools provide the interactive mechanical workspace. Save the
document as FCStd to resume later.

Select two occurrence containers (or their geometry children) and choose
**Measure SPIKE Solid Clearance**. The workbench computes minimum separation
and common solid volume. Zero separation can mean touching or intersection;
positive common volume distinguishes volumetric overlap. Measurements apply to
the represented geometry, not omitted components, holes, fasteners or cables.
Changing a placement invalidates previously measured pairs.

Choose **Send Placement Feedback to SPIKE**, save the JSON and return to SPIKE.
Choose **Review FreeCAD feedback** to see label changes, XYZ changes, complete
before/after rotation matrices and available measurements. **Apply reviewed
placements** commits the entire validated proposal to the existing occurrences.
Unchanged reimport does not rewrite the project. Feedback from a different
electrical revision or changed assembly is rejected; export a new session.

Geometry editing, occurrence addition/deletion and reparenting are deliberately
rejected by this placement feedback version. New mechanical geometry can use the
existing **Export SPIKE Assembly** / **Import board / external assembly** path;
that path adds occurrences rather than replacing existing ones. Native FreeCAD
assembly-workbench constraints/App::Link variants have not been qualified for
session feedback. Do not interpret the presence of FreeCAD's tools as support
for importing their constraint history into SPIKE.

## Geometry and results

Retained STEP part assets are digest-checked and embedded. Board bodies require
an explicit outline and complete positive physical stackup thickness. They are
extruded solids with a disclosed datum: source XY, stack top at Z=0, thickness
toward +Z, matching the existing mechanical export projection. Confirm the datum
against component and enclosure models before interpreting a physical fit.
Components, patterned copper, pad/via drills and flex bends are not included.
Missing board geometry and non-STEP parts are exported as placement origins;
no bounding box is invented as exact geometry. Such occurrences cannot be used
for solid clearance measurement. Harness connectivity/routes stay in SPIKE.

Placement changes preserve the old assembly and active result context under
`extensions.spike.mcad-collaboration.previous_states` in the project. Active
results are cleared so they cannot overlay moved geometry. This archive currently
has no dedicated restore UI; original result artifacts remain retained. Labels
alone do not invalidate results. After moving parts, review harness routes,
thermal contacts, electrical bonds, topology selectors and meshes before solving.
Existing geometry/solver qualification gates still apply.

Clearance observations return as external, unverified measurement data. They do
not establish a tolerance-stack, electrical clearance/creepage rule, connector
mating specification or manufacturing acceptance. With placement changes they
are recorded in the audit event; a measurement-only review does not modify the
project. No thermal simulation is executed by these new commands.

## Additional collaboration avenues

| Task | Available foundation | Next capability to develop |
| --- | --- | --- |
| Multi-board packaging and enclosure fit | Place occurrences, retain STEP parts, measure pair separation/overlap, return placements | Full component-model projection, assembly-wide interference review, selective structural updates |
| Connector access, service space, heatsink clearance | Model explicit service/tool envelopes as STEP parts and position them with the board | Named clearance rules, connector exit frames, mating and insertion travel checks |
| Mounting patterns, standoffs and screw access | Interactive FreeCAD modeling plus separate new-part assembly import | Hole/slot proposals tied to source board IDs; ECAD-side review and mechanical rule feedback |
| Harness packaging | Existing SPIKE pin maps/routes and board placement feedback | Routed cable solids, bend-radius constraints, clips and termination frames, reviewed route updates |
| Thermal model preparation | Source identities, assembly placements and separate thermal contracts | Equivalent anisotropic PCB solids, explicit power/contact transfer, FreeCAD FEM setup and mapped results |
| Mechanical/electrical change review | Revision binding, immutable electrical sources and placement diff | Conflict-aware three-way merge, component/keepout proposals and source-EDA acceptance |
| Fixtures, test access and panel handling | STEP fixtures and repeated board occurrences | Probe/testpoint mapping, tooling access and panel-to-board occurrence maps |
| Mass properties and tolerance studies | Placed source solids and stable occurrence IDs | Density provenance, mass/centre-of-gravity/inertia reports and parameterized fit sensitivity |
| Flex motion and assembly sequence | FreeCAD mechanical editing and static placements | Qualified formed-board geometry, bend constraints and saved assembly configurations |

The first implementations of new tasks should reuse session identity, units,
revision checks and review presentation. Structural changes, harness route edits,
ECAD proposals and solver results need their own typed contracts rather than
being disguised as rigid placements.

## Contracts and implementation

- [Session schema](../schemas/mcad-session-v1.schema.json) and
  [feedback schema](../schemas/mcad-feedback-v1.schema.json): millimetres,
  right-handed Z-up, row-major parent-local proper rigid transforms; 32 MiB JSON,
  130 occurrences, 100 STEP assets, 100 measurements. These are transport ceilings;
  project resource admission remains separate.
- No payload-specified host paths, scripts or macros are executed. STEP data uses
  fixed Part import APIs in FreeCAD. Duplicate JSON keys, unsupported fields,
  non-finite numbers, reflections, scales/shears, missing assets and cycles fail.
- The native host requires the approved project path and opened manifest binding.
  Applying feedback requires the existing `project.write` capability and the
  digest of the reviewed proposal. Digests establish identity, not publisher trust.
- [Worker service](../python/spike_core/service_mcad_collaboration.py),
  [SPIKE UI](../app/src/FreecadCollaboration.tsx), and
  [FreeCAD companion](../integrations/freecad/SPIKEWorkbench/spike_freecad/collaboration.py).
- The dependency-free validator is mirrored into the installable workbench by
  `scripts/sync_freecad_contract.py`; a regression requires byte parity. Schema
  copies are generated by `scripts/generate_mcad_session_schemas.py`.

The implementation uses FreeCAD's public placement, BREP serialization,
`distToShape` and boolean-intersection APIs. BREP identities are normalized through
a read/write cycle so unchanged FCStd save/reopen does not look like a shape edit.
[FreeCAD TopoShape API](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/TopoShape_API.md),
[public BREP string API implementation](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Part/App/TopoShapePyImp.cpp).

## Validation

`python -m unittest discover -s tests/python -p test_mcad_collaboration.py -v`
exercises session/schema validation, retained STEP identity, repeated boards,
revision conflicts, placement policy, atomic rejection, reviewed-input binding,
idempotence, electrical preservation and result-context archiving. Its installed
FreeCAD test covers generated solids and embedded STEP, separation and overlap,
nested rotation/translation, FCStd save/reopen, return to SPIKE and rejection of
geometry/structure changes. Headless FreeCAD 1.1.3 on Windows is the exercised
runtime; native GUI interaction and other FreeCAD versions need release testing.

The completed check set is 61 Python tests (including existing assembly and
workbench regressions), 35 native-host tests with one unrelated live-counter
test ignored, TypeScript, the Vite production build, generated help and the
architecture guard. Vite completed with its existing large-chunk warnings.
The source desktop has been built through the frontend; no new frozen Python
worker, native application release installer or installed workbench replacement
is claimed. [Validation record](validation/freecad-collaboration-20260907.json).

The installable ZIP is `artifacts/freecad/SPIKEWorkbench-0.2.0.zip`. Recreate it
with `python scripts/package_freecad_workbench.py --output <new-zip-path>`.
Create a runnable synthetic example with
`python examples/mcad/run_collaboration_demo.py --output <new-directory> --freecad`.
The example contains `two-boards.spike`, `two-boards-session.json`,
`two-boards.FCStd` and feedback recording a 15 mm gap. It contains no circuit or
thermal qualification data.

See the [thermal companion plan](FREECAD_ASSEMBLY_THERMAL_EXTENSION_PLAN.md) for
the remaining thermal preparation, execution and field-import milestones.
