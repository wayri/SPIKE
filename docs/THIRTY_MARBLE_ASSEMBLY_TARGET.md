# Thirty Marble-scale boards: implementation target

Requested 2026-09-06. This is a delivery target, not a claim of qualification.

## Required acceptance evidence

1. Retain and reopen 30 board instances with stable design/instance identities,
   up to 32 copper layers each. Repeated designs should share immutable assets.
2. Place, rotate and stack boards without modifying their local geometry; save
   and reopen all assembly transforms. Verify world/local picking and probes.
3. Create connector-bound harnesses with explicit pin maps, return paths and
   electrical parameters; highlight endpoints and routes across boards.
4. Render the full assembly on the EM table with consistent units and transforms.
   Table placement is not proof of a valid electromagnetic domain or excitation.
5. Run independent and coupled PI/SI as distinct workflows. Qualify port binding,
   coupling, cancellation, result provenance and conservation independently.
6. Measure cold import, reopen, peak RAM/VRAM, frame-time percentiles, picking
   latency, mesh time and solve time at 1/10/20/30 boards on recorded hardware.
   No performance pass threshold has yet been measured or agreed.

## Current implementation and gaps

- Assembly structure supports retained board identities, numeric XYZ/rotation
  editing and harness records. These controls need full 30-board visual testing.
- The count ceiling is raised to 30 consistently; resource budgets remain
  enforced. A count admission test is not a throughput benchmark.
- Independent SI batching is sequential and budgeted. It is not cross-board EM.
- Marble single-board DC has unresolved connection-evidence/branch limits.
  Resolve scoped geometry transport and scalable meshing before full-assembly DC.
- AC currently estimates a dense PEEC workspace quadratic in retained primitives.
  Sparse/block operators, reduced port models and bounded field partitions are
  needed; increasing the memory ceiling is not an implementation of these.
- General PCB-to-full-wave-to-far-field and qualified coupled harness execution
  are not established. Preserve their capability checks.

## Reproducible planning probe

`python scripts/benchmark_marble_assembly_admission.py` reports admission estimates
for 1/10/20/30 copies of Marble's recorded entity counts. It uses a declared
32 GiB budget and hypothetical 64 GiB machine, not detected user hardware.
It does not load board geometry, allocate a solver matrix, render a scene, or
produce electrical/thermal results. Use the Marble checkpoint for actual tests.

The 2026-09-06 count-proxy run estimated 3.472 GiB for visualization,
41.246 GiB for DC, 60.687 GiB for thermal and 112.421 GiB for full-wave at
30 instances. Dense AC estimated 173,569.461 GiB, demonstrating why that
formulation cannot be admitted for this all-primitive workload. These are
estimator outputs, not measured allocations, performance or validated mesh sizes.
Only visualization passed the hypothetical 32 GiB budget at 30 instances;
resource admission does not make an unavailable solver executable.
