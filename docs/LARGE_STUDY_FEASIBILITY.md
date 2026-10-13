<!-- SPDX-License-Identifier: Apache-2.0 -->
# Large study persistence, adaptive resolution and segmented multiphysics

Feasibility study — 2026-10-10. This document proposes development; it does not
claim implemented crash resume, arbitrary coupled blocks or new validated physics.

## Decision

Proceed in stages: durable incremental results first, fixed-mesh restart for
qualified solvers second, regional sizing and verified adaptivity third, and
iterated multiphysics time windows before spatial domain decomposition.

| Requested behavior | Feasibility | Current SPIKE evidence | Principal gap |
| --- | --- | --- | --- |
| Preserve data after a solver/UI crash | High | SPIKES recoverable waveform chunks, process boundaries and final project replacement | No universal durable multiphysics state/result commit |
| Resume an interrupted solve | Conditional per engine | In-process native PWM snapshot/restore | Portable complete state, compatibility and restart validation |
| Fine mesh near selected areas, coarse elsewhere | Existing experimental foundation | PCB focus sizing and graded Gmsh volume fields | Unified assembly authoring and solution-driven refinement qualification |
| Coupled simulation in successive time blocks | Good for selected physics | Experimental PWM/retained-solid window iteration | Durable state and broader solver adapters |
| Divide an assembly into coupled spatial blocks | Feasible but substantial research/engineering | Independent-job pool, retained occurrence identities | Conservative interfaces, global solve/convergence and domain partitioning |

## 1. Preserve work continuously rather than attempt to save during a crash

A crash handler cannot reliably recover RAM after forced termination, OOM or
power loss. Persist incrementally while the solver is healthy. Preserve every
successfully committed output; distinguish the current uncommitted step from
recoverable output. Even synchronous writes cannot guarantee survival of faulty
storage or every hardware power-loss scenario. State the durability boundary.

Reuse `python/spikes/waveform_store.py` where its uniform waveform schema fits:
its independently decodable, CRC-protected lossless chunks and streaming reader
already recover preceding complete chunks before a torn tail. This is a useful
result-storage foundation, not checkpointing of solver/controller/mesh state or
a globally committed multiphysics window. Extend/adapt existing contracts rather
than build a duplicate waveform format.

For coordinated field histories and restart data, use a supervised run directory
with immutable, numbered binary chunks and a
small committed manifest. Write each chunk to a temporary file, flush using the
platform durability API, verify size/digest, publish it, then durably publish
the new manifest. Recovery accepts only a contiguous valid commit chain and
ignores incomplete tails. Never overwrite the last good checkpoint. Qualify
Windows NTFS and each supported filesystem; rename alone is not a power-loss
proof. SPIKE's current project writer uses temporary ZIP plus `os.replace`,
which is final publication rather than a live checkpoint journal.

Keep full result chunks separate from restart state. Both need request, mesh,
material, contact, source and solver/version hashes, units, occurrence identities,
time/window sequence and explicit status. Raw trial iterations/logs may be
retained for diagnostics but must never appear as converged results. Offer
`running`, `interrupted — partial`, `resume available`, `restart required`,
`failed — partial preserved`, and `complete` in Studies and Results.

Saving all requested data is a storage policy, not unlimited capacity. Estimate
space and checkpoint overhead before starting; use lossless compression,
configurable output cadence and selected diagnostic fields with explicit user
agreement. Never silently downsample or discard existing data on quota failure.
Disk-full should pause/stop at a safe boundary, preserving old chunks and showing
which last step is durable. Test the reserve for manifest/checkpoint publication.

Keep active bulk data outside the `.spike` ZIP, under a project-bound run store;
package immutable chunks on Save/Export, with embedded or explicitly linked
modes, digest inventory and missing-chunk diagnostics. A linked study must not
look portable when its data was omitted. Rewriting a growing archive per step
would amplify I/O and failure exposure. Reuse archive path/size/security limits.
A future format revision must migrate old projects without inventing resume state.

HDF5 SWMR can support live readers with ordered metadata publication, but its
filesystem semantics and flush requirements must be qualified; it is not by
itself a portable solver checkpoint or proof that every last write survived.
See [HDF Group SWMR documentation](https://portal.hdfgroup.org/documentation/hdf5/latest/_s_w_m_r_t_n.html).
For the first milestone prefer a small chunk/manifest protocol with no new
container dependency; compare HDF5 only after measured access/storage workloads.

## 2. Restart requires more than saved plots

A thermal restart needs temperature/state, simulated time, integrator history,
mesh ordering, material laws and boundary/source schedule position. A circuit
restart also needs capacitor charge, inductor flux/current, device/internal
states, control-loop integrators, event queue, integration history and any
random state. CFD/EM may need velocity, pressure, turbulence variables,
electromagnetic fields, absorbing-boundary history and engine-specific data.
Store required solver state, not native pointers or a screen frame.

Each adapter must declare `results_only`, `restart_from_checkpoint`, and
`rollback_within_window` separately. Verify hashes and state schema before
resume; fail closed on changed geometry, solver ABI or incomplete state. Default
to the same admitted engine/version. Explicitly choose resume from the last
committed boundary; do not silently rerun with different settings. Reconstruct
matrix/preconditioner caches unless validated serialization warrants retention.

Current PWM volume coupling restores native snapshots during iteration and
returns committed windows on cancellation. Its documented contract explicitly
excludes portable restart. Stderr progress flushing is transport, not disk
persistence. Inspect engine restart support independently before exposing a
universal Resume button.

Specific current limitations: `assembly_tetra_transient.py` retains frame
history in RAM and does not return partial history on cancellation. Its budgets
include 10,000 steps, 1,001 frames and 200,000 node-frame values. The older
`pwm_electrothermal.py` has a digest-bound cycle token, but restoration replays
from cycle zero and claims no replay speedup; it is not a complete durable native
snapshot. Large-study support must change storage/admission contracts with
bounded out-of-core readers, rather than simply increasing these caps.
The independent local pool also has bounded job payloads/timeouts and excludes
assembly tetra/PWM volume solves from its current child allowlist; its
provenance does not claim an enforced process memory limit. It cannot currently
be used as a general large-domain solve backend.

## 3. Regional sizing and adaptive resolution

Existing [focused PCB volume meshing](PCB_FOCUSED_VOLUME_MESHING.md) selects
nets, sources and manual boxes, uses graded fine/coarse sizes, and preserves the
complete geometry. `pcb_focus_sizing.py` uses conservative bounding boxes;
`gmsh_occ_mesher.py` installs Gmsh size fields. These are not an a posteriori
error estimator or proof of convergence. Gmsh provides spatial background-size
fields; see the [official manual](https://gmsh.info/doc/texinfo/gmsh.html).

Extend the same authoring to occurrence-bound pads/vias, components, contacts,
harness endpoints and enclosure regions, with preview of requested versus
achieved mesh size, quality and cost. Coarse areas still need to resolve thin
layers, return paths, contact geometry, skin depth, electromagnetic wavelengths
and relevant thermal/fluid gradients. Visual importance is not numerical importance.

Then add solver-specific error indicators and refine/solve/assess cycles.
Thermal gradients/flux jumps, electrical loss/current crowding and EM/CFD
indicators require different estimators. Start with remeshing between complete
solves, not during a transient. Later transient remeshing needs conservative
state transfer, charge/energy/mass preservation, contact/terminal remapping and
transfer-error evidence; it invalidates old matrix/index caches and creates a
new mesh epoch in every result/checkpoint. Multirate time steps are a separate
control from spatial cell size. Retain explicit budgets and stop with evidence
when the requested accuracy is unaffordable.

## 4. What a simulation block means

### Time windows: recommended first

Each block covers `[t_n, t_n + ΔT]` and contains admitted electrical, thermal
and other supported subsolves. Save all participant states at the window start.
Exchange losses, temperatures and declared interface quantities. Re-run the
same window from those start states until coupling defects and conservation
checks pass, then commit outputs and the next restart state together. Electrical
substeps may be much smaller than thermal ones; preserve switching/event timing
and integrated Joules rather than confusing sample power with window energy.

A later time window affects the future state. It cannot simply overwrite an
already accepted earlier window: if hindsight shows that boundary interpolation
or coupling was inadequate, invalidate dependent windows and replay from an
explicit earlier checkpoint. Never combine inconsistent histories.

Implicit partitioned coupling with iteration checkpoint/rollback is an
established approach. [preCICE's official tutorial](https://precice.org/couple-your-code-implicit-coupling)
requires restoring sufficient state and only advancing accepted windows. SPIKE's
current PWM volume workflow provides a bounded starting example, not support
for every requested PI/SI/EM/CFD combination. Assess a preCICE adapter separately
for licensing, packaging and supported engine APIs before selecting it.

### Spatial blocks: separate, more difficult milestone

Boards, package groups or fluid regions can be separate subdomains. Solve block
A, exchange interfaces with B, then recompute A and B until the global interface
conditions converge. A single sequential pass generally does not establish a
coupled solution. Preserve global voltage references/return paths, charge and
current balance, equal/opposite heat flux, fluid mass/pressure conditions and
appropriate electromagnetic interfaces. Return paths, mutual inductance and
radiated fields may be nonlocal; proximity or equal net names cannot define an
interface or justify neglecting cross-block effects.

Use an explicit interface graph and conservative mesh-to-mesh maps. Serial
block iteration is a low-complexity first experiment; parallel block iteration
needs relaxation/acceleration and can converge differently. Dense coupling or
large interface exchange may erase memory/runtime gains. Existing cluster job
scheduling handles independent jobs; it is not domain-decomposed linear algebra
or a coupled MPI solver. A scheduler must fence stale/duplicate results, bind
commits to run/window/iteration/mesh IDs, and fail or retry all dependent work
from a shared accepted boundary after node loss.

## 5. Storage and cost example

One scalar float64 field on one million nodes is 8 MB per frame before metadata
or compression. Ten thousand frames require 80 GB; five such fields require
400 GB. Restart snapshots add state beyond displayed fields. For 100 independent
time chunks, each with 100 frames, output buffering alone becomes 0.8 GB per
scalar chunk, rather than retaining 80 GB of history in memory. This does not
reduce the working memory needed to solve the one-million-node domain.
Spatial partitioning may reduce per-worker solve memory, but adds interface
storage, communication and repeated iterations. Measure full wall time,
peak RAM, disk use, checkpoint latency and accuracy; no speedup is assumed.

## 6. Development and acceptance gates

1. Durable run-store prototype for one existing thermal solver: kill process
   during chunk write/manifest publish, corrupt/truncate tails, simulate disk-full
   and interrupted UI; recover exactly the last valid committed outputs.
2. Fixed-mesh restart: interrupted/restarted versus uninterrupted thermal runs;
   source events and nonlinear radiation cases; matching histories within declared
   numerical tolerance, preserved energy ledger and provenance. Then native PWM
   device/controller state round-trip and repeated restart checks.
3. Regional sizing: whole-domain coarse/focused/fine comparison at fixed physical
   probes; verify contacts/thin features, ownership, quality and an authored
   discretization tolerance. Add solution-driven remeshing only with transfer tests.
4. Time-window coupling: compare against smaller-window/smaller-step and available
   independent reference solves. Test strong feedback, nonconvergence, rollback,
   cancellation, duplication and crash at every commit stage.
5. Spatial prototype: two thermal solids with an analytical contact oracle,
   then two explicitly connected electrical boards. Compare with the same
   monolithic problem and refine interfaces. Defer EM/CFD blocks until their
   global interface/state contracts and reference tests exist.

Completion evidence must separate filesystem recovery, restart correctness,
mesh/window convergence and physical model validation. Knowledgeable human
review of numerical implementation remains required before release. No solver
code or new execution capability is implemented by this feasibility study.

## Existing implementation references

- `python/spikes/waveform_store.py`: recoverable bounded waveform chunks.
- `python/spike_core/project_package.py`: temporary ZIP/final replacement.
- `python/spike_core/worker_progress.py`: bounded correlated stderr frames.
- `python/spike_core/pwm_volume_electrothermal.py`: committed window iteration.
- `python/spike_core/retained_thermal_step.py`: conservative solid energy mapping.
- [PWM volume coupling](PWM_VOLUME_ELECTROTHERMAL.md).
- [thermal time-refinement checks](THERMAL_ACCURACY_CHECKS.md).
- [parallel worker manager and limits](PARALLEL_WORKER_MANAGER.md).
