# PCB conductor mesher optimization validation (2026-10-12)

## Scope and result

This validation covers the internal `hybrid_mesh` electrical conductor graph
for one retained real Arduino 4 Relays Shield board and a separate Gmsh OCC
tetrahedralization of eight retained copper solids from the same study. The
internal before/after rows are equivalent algorithms. The Gmsh row is a
different CAD-volume task and is not a faster/slower competitor.

The accepted internal change rejects polygon edges whose rounded x or y
displacement interval proves that the established point-to-segment distance
cannot be within the containment tolerance. For one axis, the implementation
uses the same rounded values as the legacy calculation:

```text
delta  = end - start
offset = point - start
t      in [0, 1]
```

Rounded `t * delta` lies in the rounded interval between `0` and `delta`.
Distance from `offset` to that interval is therefore a conservative lower
bound on `abs(offset - t * delta)`. An edge is skipped only when this lower
bound is greater than the tolerance. Non-finite rounded differences fall back
to the legacy distance calculation. The optimization changes neither the
point-in-polygon crossing test nor the accepted distance predicate.

## Reproduction

Run from the repository root on Windows:

```powershell
.venv\Scripts\python.exe scripts\benchmark_pcb_mesher.py `
--output "$env:TEMP\spike-pcb-mesher-benchmark" `
  --gmsh-python C:\Users\yawar\AppData\Local\Programs\Python\Python311\python.exe
```

The benchmark refuses to overwrite its output directory. The recorded result
is the unbundled local `pcb-mesher-benchmark/benchmark.json`, SHA-256
`3c8a64a41054a463e90187febadf3162c55e4dda85c6e67bdbaa89d6eb06a866`.
The optimized `hybrid_mesh.py` SHA-256 during the run was
`c60b6d5e45e808db406ad53cd77a6e8293fbce77339e82a370bcbac0fcc0764c`.

The internal fixture is the retained shield board
the unbundled local `arduino-em-20261011/prepared-final/shield-source.kicad_pcb`.
The curated source workflow and third-party provenance are documented in
`examples/multiboard/arduino/README.md` and `THIRD_PARTY_NOTICES.md`. The run
selected GND with `target_size_mm=1.0`, `zone_cell_mm=0.5`,
`max_zone_cells=3000`, `max_conductors=100000`, and a 2048 MiB admission
budget. Each algorithm used three isolated cold processes plus one warmup and
three measured warm meshes in one process.

## Internal equivalence and performance

Both rows emitted the same complete serialized mesh SHA-256
`e87eaf263533dbed6a805a27d96e68c41dc82bc4520652177b5c049e329221d6`:
681 nodes, 756 branches, 978 cells, and `truncated=false`. This byte equality
includes node and branch ordering, topology, cells and fragments, geometry
counts, issues, net/layer ownership, source IDs, attachment evidence, and
electrical branch values.

| Measurement | Legacy reference | Optimized | Ratio |
| --- | ---: | ---: | ---: |
| Warm meshing median | 1.1833781 s | 1.0396310 s | 1.1383x speedup |
| Cold process wall median | 2.4467524 s | 2.2288418 s | 1.0978x speedup |
| OS-reported peak working set | 83,259,392 B | 83,636,224 B | 1.0045x optimized/legacy |
| Sampled peak current private usage | 1,108,242,432 B | 1,109,606,400 B | 1.0012x optimized/legacy |

The Windows working-set counters cover the complete isolated worker, including
interpreter startup, imports, board import, and meshing. `PrivateUsage` is the
current private commit reported by Windows and includes runtime/import
overhead; it is not a mesh-only allocation. The change has no demonstrated
memory reduction.

The retained repeated-instance checks produced identical per-instance hashes:

| Instances | Total time | Per instance | Aggregate nodes / branches / cells | Peak working set |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 11.1479277 s | 1.1147928 s | 6,810 / 7,560 / 9,780 | 97,529,856 B |
| 20 | 21.5068974 s | 1.0753449 s | 13,620 / 15,120 / 19,560 | 115,949,568 B |

These rows retain independent equivalent board meshes in one process. They do
not build assembly-wide contact topology and report `unified_contacts=false`.
All instances were complete and untruncated.

## Gmsh boundary

The installed, hash-pinned Gmsh 4.15.2 CPython 3.11 runtime meshed a typed
eight-solid copper prefix of the retained 428-solid OCC request. It completed
in 2.9341170 s inside the adapter (4.0639350 s wrapper wall time), producing
2,017 vertices and 3,943 tetrahedra. CAD volume was
3.155038425751173 mm3 and summed tetrahedron volume was
3.1550384257511714 mm3. The minimum mean-ratio quality was
0.00018654658020312721, so this run is performance and conservation evidence,
not a mesh-quality or physics qualification.

Gmsh produces a volume tetrahedralization; the internal mesher produces an
electrical resistor graph with source ownership and terminal attachments.
Their counts and times are not semantically comparable, and the report marks
the Gmsh row `winner_eligible=false`. The pinned runtime owns a nested
resource-limited worker. This harness records wrapper memory separately and
leaves `mesher_process_memory=null`; it does not infer nested Gmsh peak memory.

## Regression evidence and limits

The focused regression module compares against the pre-change predicate and
checks:

- deterministic point/polygon equivalence at boundary tolerances, including
  large-offset cancellation counterexamples;
- 1,000 seeded segments spanning binary exponents -1070 through 999, using the
  exact legacy distance and its adjacent `nextafter` tolerances, plus overflow
  and subnormal squared-length cases;
- byte-exact full meshes for non-convex zones, disconnected clipped fragments,
  a drilled pad, a plated via, and two copper layers;
- analytic straight-trace DC resistance conservation.

Commands run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.python.test_hybrid_meshing_performance_equivalence `
  tests.python.test_hybrid_mesh_containment `
  tests.python.test_hybrid_zone_face_width `
  tests.python.test_hybrid_pad_zone_coupling
.venv\Scripts\python.exe scripts\check_architecture.py
```

The focused suite passed 28 tests and the architecture check passed. A larger
custom-pad parser selection could not create Windows temporary files inside the
managed sandbox and failed before assertions; those custom-pad cases passed in
the final repository-wide run outside that restriction. Full discovery ran
3,460 tests with two failures, nine errors and 51 skips; all new mesher tests
passed. The unresolved schema/SI fixtures, missing SIN native exports and the
debug timeout observation/reruns are recorded in
[the integration report](INTERNAL_MESHER_OPTIMIZATION_20261012.md).

This is one board/net/configuration on one Windows host. The timing ratios do
not establish a universal speedup, assembly contact support, solver accuracy,
convergence, or production qualification. Numerical code still requires the
knowledgeable human review specified by `CONTRIBUTING.md` before release.
