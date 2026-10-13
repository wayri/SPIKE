# Gmsh Volume Mesher extension

This first-party Apache-2.0 adapter generates actual first-order tetrahedral
meshes through SPIKE's existing optional Gmsh/OCC development process. Gmsh is
separately installed software under its upstream GPL/commercial terms. This
package includes no Gmsh runtime and makes no redistribution approval claim.
See `THIRD_PARTY_NOTICES.md` and `gmsh_occ_runtime.py` for the admitted 4.15.2
entry artifacts and the limits of their hash admission.

## Contributions

| ID | Result |
| --- | --- |
| `gmsh-probe` | Runtime availability and bounded geometry capabilities |
| `gmsh-prepare-pcb` | Complete normalized copper/layer/via solid job; no execution |
| `gmsh-mesh-pcb` | Actual `spike/gmsh-mesh/v1` volume mesh |
| `gmsh-mesh-assembly` | Manifest-bound retained board/STEP thermal handoff |

The PCB contributions accept `parameters.request` in the existing
`spike/pcb-volume-mesh-request/v1` contract. Preparation returns the worker's
canonical design binding; generation requires `parameters.expected_design_sha256`
matching that binding. The generation contribution also accepts bounded `timeout_s` and
`memory_limit_mb`. `examples/pcb_focus_mesh/whole_board.json` demonstrates the
normalized request. The adapter preserves unselected nets, all layers, copper
polygons, plated via spans and drill volumes. Focus selections affect sizing;
they do not crop conductors. Normalized geometry is supplied explicitly and
bound to the current design; this does not claim automatic lossless source
conversion from every supported EDA format.

The returned `solver_mesh` is the existing `spike/solver-mesh/v1` contract in
millimetres. Complete exterior triangles, CAD/material interfaces, fragment
ancestry, object/net/layer ownership, quality/volume metrics and request/job
digests accompany it. `nodes_mm`, `tetrahedra`, and `triangles` are exact full
display projections checked against that mesh, never sampled solver input.
The extension envelope and complete mesh are bounded to 8 MiB; oversized
results fail rather than truncate. Mesh/source admission verifies positive
tetrahedra, complete exterior coverage and current design identity. It does
not establish geometric convergence or field-solver qualification.

The assembly contribution accepts `project_path`,
`expected_manifest_payload_sha256`, `assignments`, and `mesh_options`, using
the existing project service's manifest checks and source reader. It supports
reviewed effective-layer boards and exact single-closed-solid STEP parts.
Assembly occurrence identity, model/occurrence rigid transforms and source
and stack digests are preserved. Board-internal decorative component models
are not automatically promoted. See `docs/ASSEMBLY_THERMAL_MESHING.md` for
those approximation and unsupported-geometry boundaries.

## Runtime and solver scope

The supported development runtime is Windows CPython 3.11 with the existing
hash-admitted Gmsh installation. A desktop running a different Python uses the
fixed `LOCALAPPDATA/Programs/Python/Python311/python.exe` installation if
present. It launches only repository-owned bootstrap code with `-I -S` and
direct package-directory insertion; it does not execute `.pth` files. No
caller executable, shell command, GEO script or Python source is accepted.

Each actual OCC operation retains the existing resource-contained child
process. The fixed interpreter bridge uses a 900-second wall-clock bound;
Windows does not support this adapter's nested Job configuration. The bridge
has bounded input/output files but no separate OS memory Job. This is not a
filesystem/network sandbox. Missing dependencies and unsupported systems
remain unavailable; no runtime is downloaded or silently installed.

Declared mesh routes cover Mesh, PI, thermal, EM and SI geometry. Compatible solver
lists are empty deliberately: thermal needs explicit materials, sources,
boundaries and contacts; Maxwell/SI need their own reviewed translators,
terminals, air regions and boundary conditions. Geometry creation never
returns an AnalysisResult or claims a field solution.

## Verification

`tests/python/test_gmsh_extension.py` checks manifest routes, no-solve behavior,
stale bindings, malformed geometry and script rejection. Its optional real
test runs an original 2 x 2 x 1 mm normalized board containing a copper pad,
plated via, drill region and dielectric layers, then re-admits the generated
tetrahedra and verifies every source owns cells and total volume is 4 mm³.
It also rejects missing boundary faces, corrupted topology, changed design
identity and false solved claims. These are bounded original fixtures, not
production CAD or solver qualification.

`app/src/GmshPcbMeshSetup.tsx` provides an explicit normalized request editor
and worker preflight. Edits or a different active board retire prepared
generation parameters. It obtains the canonical design digest from Python;
the webview does not duplicate source parsing or numerical geometry rules.
