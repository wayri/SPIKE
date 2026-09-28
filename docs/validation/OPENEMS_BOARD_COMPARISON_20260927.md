<!-- SPDX-License-Identifier: Apache-2.0 -->
# openEMS extension board comparison probe (2026-09-27)

## Scope and method

This is an execution and admission probe, not a SPIKE-versus-openEMS board
accuracy benchmark. The installed openEMS 0.0.36 runtime was discovered as
`experimental` with SPIKE adapter 1.2.0. The existing simple-patch benchmark
ran real FDTD solves at 5, 4, and 3 mm mesh resolution. The KiCad boards below
were imported into DesignIR, then passed to the same openEMS adapter preflight
for one selected net at 100 MHz to 1 GHz, 11 points, and 1 mm mesh resolution.
No port coordinates, return conductors, materials, or stackup were invented.
Consequently, no listed board reached a field solve or produced board
S-parameters. The board probe is reproducible with
`scripts/probe_openems_board_readiness.py`.

All board artifacts are local evaluation inputs. This report does not add their
designs to a redistribution package.

## Executed checks

The extension and external-engine focused test suite passed 41 tests before
the admission repair. After the latest repair, the openEMS test suite passed 50 tests.
The independent simple-patch
rerun passed all three solves and its convergence gate:

| Mesh (mm) | Resonance (GHz) | Minimum abs(S11) | Runtime (s) |
| ---: | ---: | ---: | ---: |
| 5 | 2.20 | 0.135606 | 33.92 |
| 4 | 2.28 | 0.187368 | 42.16 |
| 3 | 2.32 | 0.128518 | 52.08 |

The finest-pair resonance change was 1.724% (limit 3%), and directivity
change was 1.441% (limit 10%). These checks establish real solver execution
and reference-fixture convergence for this run. The packaged evidence record
still names adapter 1.1.0; therefore the catalog leaves the adapter
`experimental`. The board-admission fixes increased the adapter version after
this solver run. A rerun of the final source is recorded below. Neither record
establishes arbitrary-PCB accuracy.

An additional real run went through `ProcessExtension.invoke("openems-si")`
with a small explicit two-conductor fixture, a 50-ohm lumped port, and 11
frequencies from 100 MHz to 1 GHz. Preflight admitted 56,576 estimated cells;
the isolated solver returned `spike/external-result/v1` with 11 finite S11
samples in 101.68 seconds and `model_status: approximate`. The largest
abs(S11) was 1.002679 at 100 MHz, slightly above the passive one-port bound.
This fixture has no independent reference or mesh study, so the completed
process/result-import path is evidence of integration only, not accuracy or
passivity qualification. Its raw response is in
`build/validation/openems-extension-end-to-end.json`.

| Board and selected net | Imported stackup | Admission result | Known translation blockers |
| --- | ---: | --- | ---: |
| Marble v1.4.4, `+1V0` | 29 entries | `can_prepare=true`, `can_run=false`; full setup/solve blocked by unsupported selected geometry | 78: 20 pad contour, 58 via padstack |
| Converted White Rabbit core, `GND` | 0 entries | `can_prepare=false`, `can_run=false`; missing physical stackup | 1,080: 378 pad contour, 9 zones without filled copper, 693 via padstack |
| HForsten VNA2, `/filter_bank/RF_IN` | 0 entries | `can_prepare=false`, `can_run=false`; missing physical stackup | 0 |
| Haasoscope Trigger v1.1, `3V3` | 0 entries | `can_prepare=false`, `can_run=false`; missing physical stackup | 6 pad contour |
| Haasoscope MAX10 ADC v9.0, `+3V3` | 0 entries | `can_prepare=false`, `can_run=false`; missing physical stackup | 11: 1 pad contour, 10 via padstack |
| Public KiCad microwave demo, `GND` | 0 entries | `can_prepare=false`, `can_run=false`; no physical stackup and no selected `GND` conductor geometry | 0 |
| MODULAR-BUS-NIB, `/12Vout` | 17 entries | `can_prepare=true`, `can_run=false`; full setup/solve blocked by unsupported selected geometry | 96: 17 pad contour, 3 padstack, 76 via padstack |

All seven boards above imported into SPIKE; the failure is openEMS model
admission. The adapter now ignores KiCad mask/paste names when checking copper
mapping, accepts tuple-form via spans for port contacts, and does not add a
redundant layer-mapping error when stackup is absent. Marble's full input
prepared a 90,905,322-byte authenticated case. Its first setup-only attempt
raised `GEOMETRY_PADSTACK_UNMODELED` in the driver; the adapter now returns a
structured `blocked` result before launch. A further correction recognizes
KiCad's `drill_shape="none"` on undrilled rectangular pads; this removed 23
false padstack blockers on Marble, 568 on White Rabbit, and both on HForsten.
No incomplete CSXCAD setup or solver result is presented as board evidence.
The nine White Rabbit objects formerly reported as invalid geometry are
unfilled zone-outline intent records preserved by the importer. They now have
the specific `GEOMETRY_ZONE_FILL_MISSING` blocker; they cannot be used as
filled copper without a verified refill or source fill export.

The preflight also correctly requires explicit 3D lumped ports before any
solve. Its resource estimates are only grid estimates; they do not prove that
the blocked geometry would be tractable after translation. The White Rabbit
source is a converted Altium board whose conversion has not been qualified for
lossless geometry and material transfer. The Haasoscope boards are converted
from Eagle; their declared KiCad copper-layer counts do not establish a
fabricated stackup. HForsten's historical KiCad file also lacks explicit
dielectric properties. These gaps require verified source material data.

## Comparison with SPIKE

There is no matched board quantity to compare. SPIKE's available Marble
PEEC/RT0 studies concern DC resistance and approximate quasistatic RLCG;
the current Marble AC route is blocked by a copper-basis geometry defect.
The pinned MODULAR-BUS-NIB DC `/12Vout` refinement study also remains below
its signoff threshold. These results cannot serve as S-parameter reference
data for an unrun openEMS port sweep. Equating a DC voltage drop or PEEC
partial inductance with an FDTD S11 value would be physically invalid.

A defensible cross-solver benchmark needs one reviewed board slice with an
explicit signal and return, matched source/load planes and 50-ohm calibration,
verified copper/stackup/material geometry in both models, the same frequency
grid, mesh convergence in both solvers, and preferably measured Touchstone
data. SPIKE's model status must remain visible beside each comparison.

## Reproduction and local evidence

Run the patch gate with
`SPIKE_STATE_HOME=<writable private state> python -m python.spike_core.cli
openems-benchmark --mesh-resolution-mm 5 4 3 --max-timesteps 50000`.
The JSON result is in
`build/validation/openems-20260927-convergence-report.json` and solver case
artifacts are under `build/validation/openems-20260927-convergence/`.
Board admission JSON is under `build/validation/openems-board-readiness/`.
The Marble setup attempt and authenticated case are under
`build/validation/openems-marble-setup-20260927/`.
The fixture provenance and prior SPIKE evidence are documented in
`docs/CERN_MARBLE_EVALUATION_20260920.md`,
`docs/validation/MARBLE_PEEC_MESH_AUDIT.md`, and
`docs/validation/MODULAR_BUS_NIB_ANALYSIS.md`.

## 2026-09-28 capability audit

KiCad's `drill_shape="none"` sentinel was incorrectly interpreted as a drilled
pad. The shared host/worker pad lowerer now accepts it only when the drill is
zero and the pad is a surface-mount rectangle. It still rejects a nonzero
drill, a through-hole pad kind, and unsupported pad contours. Retesting the
same imported nets reduced false geometry blockers: Marble 101 to 78,
White Rabbit 1,648 to 1,080, HForsten 2 to 0, Haasoscope MAX10 ADC 77 to 11,
and MODULAR-BUS-NIB 98 to 96. These counts are admission findings, not solves.

The final adapter version is 1.2.2. Its exact current driver-source hash
matches all three newly prepared simple-patch cases in
`build/validation/openems-20260928-final/`. The real 5/4/3 mm rerun passed:
resonances were 2.20/2.28/2.32 GHz; the finest-pair resonance change was
1.724% against 3%, and directivity change was 0.592% against 10%. Full JSON
is `build/validation/openems-20260928-final-report.json`. This is still a
single reference-fixture result; packaged evidence continues to name 1.1.0,
so the runtime catalog remains experimental.

Full arbitrary-board capability remains gated on the following independent
contracts and numerical evidence:

1. **Physical materials:** verified ordered stackup, copper thickness and
   conductivity, dielectric thickness and properties over the sweep. The
   current driver defaults missing material properties; no full-board claim
   may use those defaults as fabrication facts.
2. **Copper topology:** supported pad contours, plated through-hole lands and
   barrels, via layer spans, antipads, zone holes and thermal relief, plus a
   verified board outline. Each translation needs geometry conservation checks.
3. **Ports:** reviewed signal/return entities and reference planes, launcher
   model, and per-port calibration. The current lumped-port path validates
   contacts but does not prove the connector launch or return-current path.
4. **Networks and validation:** N separate excitations for a full N-port
   S matrix, identical frequency grids, mesh and time convergence, passivity
   and reciprocity diagnostics, then comparison to trusted or measured data.
   The existing simple patch exercises one port and one reference geometry.

The source files for White Rabbit, HForsten, and Haasoscope do not supply the
physical stackup fields needed by the current adapter. Those values and port
planes must come from reviewed fabrication and measurement records. No
dielectric constants, copper thicknesses, or reference planes were inferred.

## 2026-09-28 adapter 1.3.0 rerun

The shared host/worker contour lowerer now accepts undrilled KiCad circle,
oval, and roundrect surface pads. Curves are polygonized to at most 0.001 mm
radial sagitta and carry an explicit approximation warning. The worker and
host use identical source; tests compare their contours and pad contact
behavior. The CSXCAD via shell radius was corrected to its mid-wall radius,
preserving the specified drill radius and plating thickness. Full via and
drilled-pad translation remains blocked because annular lands, bore, antipads,
and layer connectivity have not been qualified. Neither change silently
promotes a blocked board to a field solve.

The installed openEMS 0.0.36 runtime completed the exact adapter 1.3.0
simple-patch reference at 5/4/3 mm mesh. Resonance was 2.20/2.28/2.32 GHz;
the finest-pair resonance change was 1.724% (limit 3%) and directivity change
was 1.003% (limit 10%). All three solves and the fixture convergence gate
passed. The JSON record is
`build/validation/openems-20260928-v1.3.0-rerun-report.json`; cases are under
`build/validation/openems-20260928-v1.3.0-rerun/`. This reference fixture
does not contain the new curved pads or a via, so it verifies adapter
execution without validating their field accuracy.

The seven imported boards were probed again with adapter 1.3.0 at 1 mm mesh
and no inferred ports or materials. The openEMS Python test suite passed 54
tests; the architecture check and desktop extension-result script also passed.

| Board and selected net | Stackup entries | Remaining geometry blockers | Other admission blockers |
| --- | ---: | ---: | --- |
| Marble `+1V0` | 29 | 59: 1 drilled pad, 58 vias | No explicit reviewed ports; `can_prepare=true`, `can_run=false` |
| White Rabbit core `GND` | 0 | 731: 29 drilled pads, 9 unfilled zone intents, 693 vias | Missing physical stackup and ports |
| HForsten VNA2 `/filter_bank/RF_IN` | 0 | 0 | Missing physical stackup and ports |
| Haasoscope Trigger `3V3` | 0 | 6 drilled pads | Missing physical stackup and ports |
| Haasoscope MAX10 ADC `+3V3` | 0 | 1 drilled pad, 10 vias | Missing physical stackup and ports |
| Public microwave demo `GND` | 0 | 0 | Missing stackup and no selected `GND` geometry |
| MODULAR-BUS-NIB `/12Vout` | 17 | 9 drilled pads, 76 vias | No explicit reviewed ports; `can_prepare=true`, `can_run=false` |

These figures are admission evidence in
`build/validation/openems-board-readiness/`, not openEMS results for the
boards. The source boards lack enough verified input to run a defensible
board-level comparison against SPIKE. A provisional dielectric stackup or
invented port would change the physical model and is not treated as board
accuracy evidence.

For example, the imported Marble `+1V0` vias specify 0.6 mm outer diameter,
0.35 mm drill, and `F.Cu` to `B.Cu` span, but no plating thickness or explicit
per-layer annular/antipad geometry. Its TP9 through-hole specifies 1.5 mm
outer diameter and 0.7 mm circular drill, again without a fabrication plating
record. A cylindrical shell built from those values alone would omit physical
copper and void topology; the geometry gate correctly prevents a solver run.

The shell correction uses the documented CSXCAD primitive invariant
`inner_radius = radius - shell_width/2` and
`outer_radius = radius + shell_width/2` from
<https://docs.openems.de/en/latest/concepts/primitives.html>. For drill diameter
`d` and plating thickness `t`, setting `radius=d/2+t/2` and `shell_width=t`
preserves the specified inner and outer wall radii in millimetres. This is an
independent geometric derivation and test oracle; the source implementation
was not copied. It does not resolve mesh representation, epoxy-filled bores,
lands, antipads, or full-wave accuracy. Numerical release still requires
knowledgeable human review.

## 2026-09-28 provisional recovery work

KiCad 10.0.6 refilled a *copy* of the converted White Rabbit board using its
native `pcb drc --refill-zones --save-board` path. The source hash was unchanged.
SPIKE re-import found 156 source-filled components versus 106 before refill,
and 7 outline-intent records versus 24 before. The selected `GND` probe now
has 3 unfilled intents versus 9 before; its other blockers remain 29 drilled
pads, 693 vias, missing physical stackup, and missing reviewed ports. KiCad's
DRC reported 2,077 violations and 50 unconnected items. The candidate and
full provenance are under
`build/white-rabbit-qualification-20260920/zone-fill-recovery-20260928/`;
the repeatable utility is `scripts/recover_kicad_zone_fill.py`. This recovery
does not qualify the Altium-to-KiCad conversion or fabricated copper.

For a runnable integration experiment, `scripts/run_openems_provisional_hforsten.py`
extracts the five source `RF_IN` track/pad records from the HForsten VNA2
board, adds an explicitly assumed local `In1.Cu` GND rectangle and 1.6 mm
four-copper FR-4 stackup, and places an uncalibrated 50 Ω lumped port at source
pad C5.1. The OpenEMS Suite process extension independently returned
`can_run=true` with no geometry blockers. The isolated adapter generated the
CSXCAD setup at 0.1 mm mesh; preflight estimated 2,533,629 cells and 649 MB.
The authenticated case, assumptions, and result are under
`build/validation/hforsten-rf-in-provisional-20260928/`. This is a local
board-derived slice, not the full VNA2 PCB or a measured accuracy benchmark.

The first fine-mesh 0.1 mm, 100 MHz–1 GHz attempt exceeded its 900 s wall
limit. It exposed a process-cleanup bug: a failed Windows `taskkill` returned
a nonzero status without raising, leaving the FDTD child alive and turning
the timeout into a misleading launch error. Adapter 1.3.1 now kills the direct
child on that path and caps process supervision by `max_solver_time_s`;
focused tests cover both conditions. The orphaned process from that attempt
was stopped. The trusted FDTD driver source hash is unchanged from the 1.3.0
simple-patch rerun, but that three-mesh gate was not repeated after the process
supervision patch. The timed-out setup is evidence only; it produced no field
result.

A bounded 0.2 mm, 1–3 GHz repeat completed real openEMS FDTD in 226.6 s.
The case estimated 323,760 cells and returned 11 finite S11 samples with
`model_status=approximate`; the sampled magnitude ranged from 0.9913 to
0.9921. The authenticated case and report are under
`build/validation/hforsten-rf-in-provisional-fast-20260928/`. No mesh
convergence, calibrated launch, fabrication material confirmation, or measured
comparison was performed for this slice, so these numbers are integration
evidence only. The chosen local GND rectangle and the short return path can
dominate the result; they must not be used to evaluate SPIKE accuracy.

Adapter-focused verification after the timeout fix passed 25 external-engine
and refill tests, 54 openEMS tests, the architecture check, and the desktop
extension-result script. A full repository Python run was attempted in both
available general environments. The project `.venv` lacks `shapely`, so PEEC
conforming tests fail at import. The system Python has `shapely` but lacks
`jsonschema` and `pyarrow`; its 1,542-test run ended with 150 errors and 23
failures, including worker-environment checks. Neither full run is reported
as a passing project gate.
