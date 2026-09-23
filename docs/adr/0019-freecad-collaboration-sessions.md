# FreeCAD collaboration sessions

Status: accepted for the source companion 0.2.0, 2026-09-07.

Add `spike/mcad-session/v1` and `spike/mcad-feedback/v1` alongside existing
assembly import/export contracts. A session preserves occurrence IDs and a
project/assembly/electrical-revision binding. Feedback changes only labels and
proper rigid local placements; it does not remap source IDs or import ECAD edits.

SPIKE performs manifest-bound export, preview and atomic apply in the Python
worker, reached through approved-path native calls. Applying uses `project.write`
and the reviewed feedback digest. FreeCAD remains an optional external application
with explicit file exchange. Discovery does not launch or install FreeCAD.

The standalone workbench and worker share a dependency-free validator through a
generated copy with enforced parity. Neither exchange loads code from JSON. New
geometry/harness/thermal semantics require new typed contracts.

Changed geometry/structure in FreeCAD and stale assembly revisions are rejected.
Full three-way merge is deferred. Read-only measurements describe the supplied
solids and remain external observations. Placement changes retain prior assembly
and result context in the project extension archive and clear active results;
they cannot make old fields valid for new geometry.

This adds contracts and optional collaboration commands without changing the
project ZIP version, solver interface or the core renderer. See
[the implemented workflow](../FREECAD_COLLABORATION.md) for source ownership and
qualification limits.
