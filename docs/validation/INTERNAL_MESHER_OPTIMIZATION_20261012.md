# Internal mesher optimization and comparison

This pass covers the bounded internal convex tetrahedral generator and the
separate PCB conductor mesher. It preserves experimental/approximate statuses,
resource limits, source ownership and the existing worker contracts. It does not
turn the convex generator into a complete nonconvex PCB or assembly CAD mesher.

## Tetrahedral implementation and derivation

Profiling the original 64-point fixture recorded 0.579 seconds, including
0.500 seconds in sphere predicates and 0.174 seconds in the four-by-four
determinant. Profiling overhead is included; these are hotspot measurements,
not before/after benchmark medians.

The generator expands the same four cofactors directly instead of allocating
four three-by-three submatrices for every determinant. Every minor retains
the original multiply/subtract/add association. The four signed terms still
use Python `sum`, preserving its version-specific floating summation behavior.
Exact `Fraction` arithmetic uses the same expressions. Per-point absolute
coordinate maxima are computed once for the immutable normalized points;
taking the maximum of these values is identical to rescanning the coordinates.
Metadata storage is O(input points), bounded by the unchanged 128-point limit
plus four enclosing points. There is no new global geometry cache.

The orientation and in-sphere determinants, conservative floating filters,
exact fallback, symbolic tie ordering, work budgets and complete output
certification are unchanged. Thus conditioning thresholds and supported units
remain those in [the engine contract](../INTERNAL_MESH_ENGINE.md). No numerical
tolerance was relaxed, coordinate jitter introduced or admission check removed.

The baseline source SHA-256 is
`4906644b110a1e024d011836537ed5042f9518f46bd20b6df199906c6fd0adec`.
The complete baseline candidates and known failure are retained in
`output/internal-mesher-benchmark-20261012/baseline-internal-preoptimization.json`.

## Correctness evidence

The focused tetrahedral gate passed 54 tests with warnings treated as errors:
generation, dynamic adaptation, worker admission, refinement and smoothing,
plus the new allocation regression. New checks compare 300 floating matrices
bit-for-bit with the original operation order, 30 exact rational matrices with
an independent permutation determinant, and complete mesh candidates, quality
and predicate counters on cube, lattice and generic-cloud cases. A known
32-point finite-enclosure failure is preserved rather than hidden.

An independent read-only review compared 3,750 predicate decisions and counters
with the complete original module across 50 varied/cospherical clouds, plus
complete candidate or rejection parity on 4/12/24/48-point inputs. No tetrahedral
finding remained. Existing tests include exact hull/cell volume, SciPy black-box
connectivity, material interfaces, affine nodal transfer, per-material integral
conservation and decreasing analytical interpolation error under refinement.
That interpolation evidence is not a PDE solver convergence claim.

## Benchmark contract

`scripts/benchmark_internal_mesher.py` uses original deterministic point clouds
and separately installed public mesher APIs. Internal kernel and worker-boundary
timings are reported separately. Gmsh and SciPy/Qhull comparisons use the same
coordinates; cospherical triangulations need not have identical connectivity.
Independent geometry auditing is separate from timed generation. SPIKE's
mandatory built-in certification remains inside its generation timing, so
cross-engine timing boundaries are explicitly different.

The harness records source/fixture digests, versions, warmup/sample counts,
timeouts, failure states, hull volume, positive cells, point retention, topology
and mean-ratio quality. Isolated process working-set/commit counters include
runtime imports; sampled growth is not a bound on peak mesh allocation. No
10 GB workload qualification or whole-application RAM reduction follows from
small convex-cloud results.

The PCB-specific implementation, real fixtures and measurements are recorded in
[PCB mesher optimization](PCB_MESHER_OPTIMIZATION_20261012.md).

## Measured internal before/after

The clean serial run used one warmup and five samples in isolated processes.
Times below include SPIKE's unchanged certification; import/startup is separate.

| Original fixture | Baseline kernel ms | Optimized kernel ms | Local speedup |
| --- | ---: | ---: | ---: |
| Generic 8 points | 2.748 | 2.010 | 1.37x |
| Generic 32 points | 59.778 | 32.832 | 1.82x |
| Generic 64 points | 258.413 | 144.611 | 1.79x |
| Generic 128 points | 1123.828 | 624.551 | 1.80x |
| Cospherical cube | 6.857 | 5.782 | 1.19x |

Every successful kernel output hash matches the baseline. The thin-conditioned
failure type/message is unchanged. Complete kernel and worker-boundary candidates
also match the pre-edit baseline on all twelve recorded rows in
`output/internal-mesher-benchmark-20261012/exact-equivalence.json`.
Small-process memory counters do not establish whole-application RAM savings.

Authoritative internal/external results and SHA-256 values are indexed by
`output/internal-mesher-benchmark-20261012/ARTIFACT_STATUS.json`. Earlier
exploratory reports remain preserved and are explicitly superseded: some
mistakenly sampled the Windows venv launcher rather than the actual worker.
Only worker self-counters are used in the final internal report. Peak resident
memory was approximately 62.8-64.7 MiB; private commit was approximately
1,041-1,043 MiB including runtime/import overhead. These different counters
must not be added together. No mesh-only peak or memory saving is asserted.

The original source is also recoverable from project commit
`537023f84e70ed0d45915c7ef2b5cdb858d18228`; its file hash is recorded above.
Reproduce current cross-engine measurements in a new output directory:

```powershell
.venv\Scripts\python.exe scripts\benchmark_internal_mesher.py --samples 5 --warmups 1 `
  --output output\internal-mesher-comparison-new `
  --backends internal_kernel internal_fullrun scipy_qhull gmsh_4_15_2
```

## External mesher comparison

SciPy/Qhull passed the independent audits for all six original fixtures. Its
generic 8/32/64/128-point generation medians were 0.631/0.851/1.011/1.492 ms;
cube and thin-case medians were 0.767 and 0.826 ms. It is substantially faster
for these point clouds. SPIKE generation includes complete built-in certification
while these external timings exclude the independent post-run audit, so the
figures do not represent equal validation pipelines or CAD meshing capability.

The hash-pinned Gmsh 4.15.2 **raw point-cloud API** passed the eight-point case
(0.081 ms, nine cells). Its 32/64/128-point returns used every original point
but failed independent hull-volume checks, with 104/270/635 cells versus
SciPy's 126/301/701. The raw volume/hull volume pairs were
0.3410362/0.3793897, 0.5222103/0.5518011 and 0.6467903/0.6922381.
Its cube output varied across all five timed samples and the final sample had
three zero-volume cells. Its thin case also failed hull coverage. Invalid
outputs remain in the evidence and are excluded from quality-qualified rankings.
Independent black-box checks confirmed one-based connectivity and no Steiner
points for these cases; no returned cell was removed to manufacture a pass.

These findings apply to that raw API and pinned installation only. The separate
Gmsh OCC/CAD PCB run succeeded and conserved volume; see the PCB report. No
claim about Gmsh's general meshing quality follows from the raw API results.

## Final integration checks

The final source passed the tetrahedral gate (54 tests), PCB gate (28 tests),
benchmark gate (11 tests), independent numerical review, architecture guard,
Python compilation and changed-file whitespace checks. These focused groups
overlap; their counts must not be summed into a unique-test total.

Full Python discovery completed 3,460 tests in 888.342 seconds: two failures,
nine errors and 51 skips. Log:
`output/mesher-optimization-python-final-tests-20261012.log`. All nineteen new
mesher/benchmark tests passed in this full run. The repository gate is not green:

- The public-release check still rejects the absent/duplicate schema ID in
  `assembly-em-request-v1.schema.json` (one failure and one error).
- Four SI analytical fixture tests still lack `signal_width_m`.
- Four SIN-source native tests report that the loaded SPIKES library lacks
  analytic SIN exports. A direct ABI test reproduced that error independently;
  those native source/binary paths were not changed by this mesher pass.
- The Python-debug hard-timeout test stayed in `starting` beyond its four-second
  wait in the broad run. Its isolated method passed, and its complete eight-test
  module subsequently passed in 14.816 seconds. The broad failure remains in the
  recorded result rather than being replaced by the rerun.

The custom-pad cases that failed temporary-file access inside the managed
sandbox passed in the full run outside that restriction. No failed test was
weakened or skipped to make the mesher optimization pass.

## Provenance and release limits

The implementation, derivation, tests and benchmark fixtures are original
SPIKE-owned work. No third-party implementation, source comments, examples or
meshes were inspected or adapted. Gmsh's public API is documented in its
[official manual](https://gmsh.info/doc/texinfo/gmsh.html); optional runtimes are
used as black boxes and are not bundled. Existing dependency licensing and
runtime admission boundaries are unchanged.

Knowledgeable human numerical review remains required before release. Mesh
validity and unchanged discretization do not expand physics validation or
establish full-board CAD/field convergence.
