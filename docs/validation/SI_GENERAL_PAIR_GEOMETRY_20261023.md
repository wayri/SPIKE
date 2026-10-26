<!-- SPDX-License-Identifier: Apache-2.0 -->
# Retained general pair geometry preparation

## Claim and boundary

`python/spike_core/si_pair_geometry.py` prepares independently segmented signal
and victim routes without discarding fan-in/fan-out, bends, vias or pad geometry.
It does not call or relax the strict/piecewise coupled channel extractor. The
output always reports `channel_extracted=false`, `production_qualified=false`
and `compliance_status=not_evaluated`, including a perfectly straight fixture.
No RLC, S-parameter, delay, eye or BER result is produced.

This is a computational geometry prerequisite, not a new electromagnetic law or
3-D field solver. Existing mesh owners are `pcb_volume_compiler.py`,
`pcb_volume_mesh.py` and the Gmsh OCC bridge, described in
[whole-board focused meshing](../PCB_FOCUSED_VOLUME_MESHING.md). They accept a
separate explicit CAD-neutral volume model, not this source partition directly.
There is no automatic retained-pair-to-volume/port translator in this increment.
Do not feed projected candidates into a quasi-TEM solver as admitted sections.

## Developer API and retained ownership

Call `prepare_pair_geometry(design: SpiDeRV2, request, cancel_check=None)` with
`signal_net`, `victim_net`, `reference_net` and `reference_layer` selectors.
Optional `terminal_pad_ids` maps `signal` and/or `victim` to two explicitly
ordered pad IDs on the corresponding net. This asserts source assignment only;
it does not prove pad contact, orientation of a field port or a compliance plane.
Absent terminal IDs remain `not_bound`. Unknown request fields fail closed.

The result retains original tracks, arcs, vias, pads, zones, associated drills
and castellations on both selected nets, including complete source metadata,
widths, layer IDs and native path membership. It also retains the complete layer
stack and global unresolved/standard-contour padstack context. Reference net,
layer and matching zone IDs are explicit but reference coverage is unverified.
The complete input design digest binds other copper, materials and external
context; the preparation is not a cropped substitute for the original design.
Downstream field preparation must load and verify that bound design.

Every selected straight source track is partitioned over its original `[0,1]`
parameter domain. Interval endpoints are exact numerator/denominator pairs.
All intervals are retained, including unpaired intervals and intervals with
multiple possible partners. Candidate geometry is not nearest-neighbor matched:
multiple parallel runs remain explicitly ambiguous. Each route records retained
3-D transition source IDs for vias, pads, arcs, zones, drills, castellations,
bends, width changes and endpoint branches. All are unextracted.

Exact endpoint incidence supplies a route order only for a connected open
track/via graph. Via edges span consecutive copper layers across the complete
declared barrel, retaining unused barrel portions rather than clipping stubs.
Branches, disconnections and arc-containing paths remain unresolved. This graph
does not prove full copper connectivity: interior track contacts, pad contacts,
overlap, zone connections and native DRC/ratsnest closure remain separate.
Arc geometry is retained verbatim without tessellation, and its total length is
explicitly unknown. Straight-centerline lengths and via axial spans are separate
observables; neither is a total electrical path length or a delay.

## Independently authored geometry formulation

For source segment `a(u)=p+u*d`, `u in [0,1]`, and another `b(v)=q+v*e`, first
require an identical layer and the exact determinant `d_x*e_y-d_y*e_x=0`.
Project the two endpoints of `b` into the first segment's parameter coordinate:
`u_i=((b_i-p).d)/(d.d)`. Intersect their ordered interval with `[0,1]`. A positive
intersection is a geometric overlap candidate. Map its endpoints back into the
second segment using `v=((a-q).e)/(e.e)`, then order those endpoints. Reversed CAD
segment orientation therefore changes neither physical coverage nor membership.
Squared centerline separation is `cross(q-p,d)^2/(d.d)`. Compare this exactly
with `((width_a+width_b)/2)^2` to flag overlapping/touching parallel strips; this
flag is not a complete footprint-clearance test at ends or bends.

For each track, take the sorted union of 0, 1 and every candidate interval
endpoint. Consecutive values partition the original parameter domain exactly;
an event sweep labels each interval with all candidate memberships. Thus
`sum(u_(i+1)-u_i)=1`, disjoint interiors and complete source coverage hold without
a matched segment-count assumption. Length is `norm(d)*(u_(i+1)-u_i)` in mm;
full track totals use compensated summation of Euclidean endpoint distances.
The 3-4-5 fanout fixture supplies an independently known 5 mm length increment.

All predicates and parameter arithmetic use `Fraction(float)` on admitted
canonical binary values: no rounding, coordinate snapping, denominator fitting
or tolerance tuning. Near-parallel native-quantized diagonals can consequently
remain unpaired. This is conservative candidate discovery, not lost geometry.
It is not claimed invariant to arbitrary floating-point coordinate transforms;
exact 90-degree and power-of-two scale cases are tested. Positive interval
lengths that underflow at the float output boundary fail explicitly.

Reviewed official primary API definitions on 2026-10-23:

- Python documentation, `fractions.Fraction` numeric construction semantics:
  [rational arithmetic](https://docs.python.org/3/library/fractions.html).
  The reviewed page identifies itself as Python 3.15.1; numeric `float`
  construction is documented as available since Python 3.2. No newly introduced
  constructor API is used by this Python 3.12 execution.
- Python documentation, `math.dist`, `math.hypot` and `math.fsum`:
  [Euclidean norm and compensated summation](https://docs.python.org/3/library/math.html).

The projection, determinant, partition proof, implementation and test fixtures
were authored independently from elementary affine geometry; no external source
implementation, example code, mesh or dataset was inspected or adapted. The
official documentation was reviewed for API/mathematical semantics only. These
references do not establish electromagnetic validity or repair existing physics
provenance gaps.

## Budgets and failure semantics

Limits: 8,192 selected sources, 256 layers, 262,144 track-pair comparisons and
partition membership associations, 32,768 candidates, 65,536 partitions and
16 MiB serialized preparation output. Coordinates and dimensions are finite and
bounded to absolute 1e6 mm. Track widths/lengths and via spans/drills must be
positive; via drill must be smaller than its outer diameter. Cancellation is
checked between signal tracks and partitioned tracks. Exact rational predicates
are quadratic in source-pair count before the fixed work limit; output event
sweeps do not perform an unbounded per-interval membership rescan.

Input normalization and full-design hashing remain ordinary Python allocations;
the serialized bound is not a process resident-memory guarantee. Use the worker
process watchdog for whole-operation cancellation/time/memory containment.
Errors abort preparation; no partially completed channel is returned.

## Executed verification

Focused reproduction:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_si_pair_geometry -v
.venv/Scripts/python.exe scripts/check_architecture.py
```

Eleven authored tests passed with zero skips. They cover unequal CAD subdivision, complete rational coverage,
unaltered source objects, real nonparallel fanout, reversed source direction,
ambiguous overlaps, retained arcs/vias, exact diagonal and near-parallel rejection,
terminal ownership, malformed coordinates/units/requests, cancellation and all
output/work budgets, rigid coordinate change, scaling and layer-transition
retention. Source fixtures are independent synthetic geometry, not measurements.
Architecture validation and focused diff whitespace checks passed. The final
integration verifier is `scripts/verify_si_pair_geometry.py`; its pinned
real-board report remains separate from the original extraction failures.

The parent integration run completed all **18 pairs** (16 Marble, 2 native
WREN-Ie), with zero lost or multiply covered straight-track parameter intervals.
The verifier compares every selected source record against the original typed
design, independently of the preparation's coverage flags. It checks board and
inspected implementation hashes before/after, preparation/design digests and
design immutability. No material overrides are applied. Reproduce with:

```powershell
.venv/Scripts/python.exe scripts/verify_si_pair_geometry.py --output build/si-pair-retention-new.json
```

The retained local report `build/si-pair-retention-final-20261023.json` is 27,559
bytes, SHA-256
`9ef711768d4111b179c0d393550177f1f285921dc8ca24948f917427f554a07f`.
It records summaries and complete-preparation digests, not an archive of solved
fields. Original board hashes remain those in
[the original admission experiment](SI_BOARD_PROTOCOL_READINESS_20261023.md).

WREN TX retains 30/35 tracks and 2/2 vias, producing 25 projected candidates and
110 full-coverage partitions. RX retains 28/29 tracks, with straight lengths
132.97084254510222/133.07102784457635 mm, 32 candidates and 118 partitions.
Marble QSFP1 RX1–3 retain unresolved endpoint topology on both polarities
(including barrel/stub branches); these are not silently simplified to open
chains. None of these observations is an electrical delay or channel solution.

Parent checks: 26 focused geometry/verifier/original-admission tests plus 67
adjacent channel, reference-zone, material, AMI and worker-snapshot tests passed
with no skips. The architecture check passed. This was scoped regression
verification, not a full-suite, packaged-worker, installer or release run. The
previous R3 frozen worker does not include this newly authored source.

## Physics still blocking a solved channel

No general nonconformal pair field extraction or 3-D bend/fanout/via/pad/antipad
transition extraction exists in this component. Reference copper topology,
dielectric dispersion/loss, conductor surface/roughness effects and broadband
material provenance still need admission. Packages, connectors, switches and
physical port/reference planes remain unbound. A suitable mesh and source-bound
full-wave/transition solver need independent convergence and correlation, followed
by real Tx/Rx/CDR/jitter/BER and normative protocol evidence. No supplied or
invented via-RLC, dielectric, return path or clock channel closes these gaps.
Human numerical/physical release review remains mandatory.
