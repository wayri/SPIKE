# Explicit tetrahedral mesh workspace

The shared Mesh workspace provides **Explicit tetra mesh** for typed
`spike/gmsh-occ-mesh/v1` requests. Polygon prisms (including holes) and analytic
tubes generate first-order tetrahedra, material ownership and interface faces.
The panel imports requests/results, displays counts and quality, and exports JSON.
It does not translate the active PCB or attach a tetrahedral mesh to PI/SI solves.
Target solver admission remains separate; PI's existing 3D hybrid graph is not
tetrahedral FEM.

CLI: `python -m python.spike_core.cli tetra-mesh --request request.json`.
Optional `--timeout-s` and `--memory-limit-mb` bound native generation. The worker
method is `generate_tetrahedral_mesh`. No caller executable or script is accepted.

Generation currently requires the existing hash-pinned Gmsh 4.15.2 installation
and Windows CPython 3.11. The current project `.venv` uses Python 3.12.9 and cannot
generate with this runner; it reports the runtime mismatch rather than substituting
another mesher. Import/export remains available. This is local development support,
not redistributed or production-qualified runtime support.

On 2026-09-20, generation using the installed CPython 3.11 produced 573 tetrahedra
and 212 vertices for the original 4 x 3 x 1 mm prism with a 1 mm square through-hole.
CAD volume was 11 mm³ and tetrahedral volume 10.999999999999995 mm³; minimum mean-ratio
quality was 0.3949723. Artifacts: `artifacts/tetra-workspace-20260920/`.
This validates a small geometric fixture, not full-board translation or physics.

Verification: 25 focused Python tests passed under CPython 3.11, and the CLI
generated the same fixture through the worker route. Frontend rendered-panel and
shared-workspace tests, TypeScript and production frontend build passed. No new
installer or full-suite qualification is claimed for this increment.
