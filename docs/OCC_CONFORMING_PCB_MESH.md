# Executed native OCC conforming PCB mesh path

SPDX-License-Identifier: MIT  
Copyright (c) 2026 SigHarmonic

## What now executes

`gmsh_occ_mesher.build_occ_mesh` generates a new CAD-conforming tetrahedral mesh
from typed polygon prisms (including concave outlines and polygon holes) and
analytic cylindrical tubes. This is geometry generation, not refinement of an
already supplied mesh. All intersecting solids are fragmented together with
OpenCASCADE; returned ancestry determines material/source ownership. Explicit
material priorities resolve overlaps; conflicting equal-priority materials are
rejected rather than selected by a centroid heuristic.

Shared CAD interfaces generate shared mesh nodes/triangles. Output includes the
existing `spike/solver-mesh/v1` data, source IDs, materials, oriented exterior
faces, interface adjacency and CAD surface tags. Independent neutral-mesh
checks verify positive finite volumes, opposite-side face ownership, complete
boundary coverage and quality. CAD source volumes are checked through Boolean
fragmentation. Linear tetrahedra approximate curved surfaces: curved material
volume error must be studied separately from total domain volume.

The exact input contract is `spike/gmsh-occ-mesh/v1`; see
`examples/mesh/pcb_occ_request.json`. Only numeric typed primitives are accepted;
no GEO/Python text, imported CAD file or arbitrary executable is accepted.

## Local runtime and limits

The existing administrator-installed Gmsh 4.15.2/OpenCASCADE installation at
`C:/msys64/ucrt64` is used from Windows CPython 3.11 in a separate process.
Nothing was downloaded, and no vendor source was copied or modified.
The runner checks exact SHA-256 identities before loading the entry artifacts:

| Installed artifact | SHA-256 |
| --- | --- |
| `lib/gmsh.py` | `f4b0935cebde899750293d87a643090e5ea33c9b18d249267f507db68a0e01c3` |
| `bin/libgmsh.dll` | `a43b4c96644b3c7dc57f79285cd68814ecb3995e582939378a27d238533ed599` |

These are **local-development pins, not release dependency approval**. The
transitive DLL set, signed dependency ledger, licenses/notices, SBOM and
redistribution remain to be qualified. Do not bundle this installation into a
release merely because the example runs. Gmsh's own licensing and documentation
remain authoritative; this process separation is not a claim of legal clearance.

The existing OS process limiter provides timeout, memory and process-tree
termination; the worker is assigned to a Windows Job Object before resuming.
This is not a filesystem/network sandbox. Only the API and main DLL are
entry-hash-admitted, not all dependent DLLs. Requests are bound by SHA-256 and
limited to 8 MiB; outputs have bounded file/control budgets. The native geometry
kernel runs under the process memory limit; mesh cell/vertex caps additionally
reject oversized generated output. At most 64 solids and 2048 polygon vertices
are supported by this development contract.

## Running and verification

```powershell
python scripts/run_occ_mesh.py --request examples/mesh/pcb_occ_request.json --output build/my-new-occ-case
python scripts/verify_occ_runtime.py
```

Output includes `mesh.msh`, `result.json`, worker/process logs and artifact hashes.
The native example actually ran with a concave board, polygon cutout, plated
via, explicit drill-air region and top copper. It produced 888 vertices,
4083 tetrahedra and 845 shared CAD-interface triangles. CAD and tetrahedral
total volumes agreed at 10.5189 mm³; minimum mean-ratio quality was 0.12006.

The executed verification additionally tested three tube mesh sizes and
equal-priority material rejection inside the native Boolean path. Tube relative
volume errors were 0.009327, 0.009511 and 0.0002124 at maximum sizes 0.2, 0.1 and
0.05 mm respectively. The finest result improved, but the sequence is **not
monotonic and is not a demonstrated asymptotic convergence order**.
Evidence: `build/occ-evidence-20260906T173122.431172Z/report.json` with stable
source hashes and per-case artifact digests.

## Still not general production PCB meshing

The caller supplies typed solids: automatic full DesignIR lowering, arbitrary
STEP/package geometry, bends, CAD healing, imported self-intersection repair,
high-order curved elements, automatic terminal/wave-port construction, layer
boundary adaptation and distributed generation are not supplied by this path.
CAD surface tags are adjacency labels, not inferred electrical port definitions.
Meshing success is not FEM/Maxwell/CFD solver accuracy or production qualification.

For enclosure work, `OPENFOAM_FAN_BOUNDARIES.md` documents the separately
prepared real heated-flow fixture. Its actual CFD execution still requires an
accessible compatible solver runtime and open-flow mass/enthalpy qualification.
OpenFOAM 2606 was located by an escalated read-only probe in Ubuntu/WSL; using
that worker for the actual solve is awaiting owner direction. The current
increment passed 44 warnings-as-errors unit/adapter tests and architecture checks.
