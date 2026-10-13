<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Coupled assembly electrothermal analysis

For the internal PI DC or SI single-frequency linear circuit coupled to retained
3D thermal volumes, see [native circuit volume coupling](MULTIBOARD_VOLUME_ELECTROTHERMAL.md).
The solid electrical-conduction path below also accepts `thermal_engine`
`internal` or `calculix`, with shared contact resistance/area admission and
temperature feedback at every thermal solve. See [CalculiX execution](CALCULIX_THERMAL.md).

The experimental worker solves steady DC electrical conduction and solid heat
conduction on supplied conforming tetrahedral volumes, including multiple board
occurrences and explicitly matched resistive bonds. Temperature changes bulk
conductivity and supplied semiconductor loss tables. This is executable coupling,
not general PCB CAD extraction or universal semiconductor coverage.

## Run the example

From the repository root run:

```powershell
.venv/Scripts/python.exe -W error examples/assembly_field/run_electrothermal.py
```

The example builds original synthetic one metre slabs, not a measured PCB.
It prints input/result digests, power, occurrence temperatures and convergence.
Two 0.5 ohm volumes and a 0.25 ohm bond at 2 V give 1.6 A, 3.2 W total heat
and 0.64 W contact heat. Further runs demonstrate temperature feedback and a
synthetic switching-loss table. These materials are not real device data.

## Worker inputs and coupling

An already generated complete `spike/solver-mesh/v1` PCB volume can now be
bound using `prepare_pcb_electrothermal_geometry` with exactly `{request}`.
The `spike/pcb-electrothermal-geometry-request/v1` envelope requires mesh,
occurrence/reference IDs, declared source digest, stack binding and exact
local-to-physical material mapping. The returned `body` can be placed in
the retained geometry `bodies` array. Derived exterior face ownership allows
explicit terminal selection; cell ownership retains net/layer/source IDs for
loss deposition. Repeated boards are separate occurrences with retained rigid
transforms, not copied result images. Complete exterior topology is checked.
This bridge does not generate a mesh from arbitrary PCB source geometry,
authenticate its declared source digest, infer contacts or run AC extraction.

Call `run_assembly_electrothermal` with exactly `{request}` through
`python.spike_core.service`. The contract is
`spike/assembly-electrothermal-request/v1`; see
`../schemas/assembly-electrothermal-request-v1.schema.json`.
Supply retained thermal geometry/problem, electrical materials, occurrence-scoped
terminal faces, matched face pairs for every electrical bond, a nonoverlapping
loss inventory and explicit iteration limits. Semantic decoders additionally
check geometry, topology, ownership, finite values and resource budgets.

Conductivity obeys `sigma(T) = sigma_ref / (1 + alpha * (T - T_ref))`.
The temperature envelope applies to cell mean temperature, not peak nodes;
the denominator must be finite and positive throughout the envelope.
Retained bond area/resistance must agree with the contact model. Bulk Joule
heat and half each contact loss on each side are deposited exactly once.
Only compiled electrical bonds are removed from the nested thermal-only
adapter; the original complete request and assembly remain hash-bound.
Unrepresented harness, connector and rigid-flex connectivity is rejected.

The fixed-point loop checks unrelaxed temperature defect and L1 electrical
power change; relaxation cannot mask failure. The nested final thermal result
used the preceding load: `coupled_power_defect_w` reports the bounded remaining
difference. Background thermal sources enter the thermal solve but not the
electrical-only `cell_deposited_power_w`. Results include conservation, history
and integrity hashes. Cancellation is polled between phases, not OS-enforced.

## Heating sources

Call `evaluate_electrical_heat_source` with exactly `{request, temperature_k}`.
The `spike/electrical-heat-source/v1` contract supports:

- Dissipative terminal waveforms: exactly integrate the product of piecewise
  linear voltage/current and reject negative-power intervals. Stored energy
  must already be separated from dissipative terminal power.
- Orthogonal RMS spectral currents and frequency-specific resistance:
  sum `I_rms^2 R`; this does not extract broadband field currents.
- Temperature-indexed conduction power and nonoverlapping turn-on, turn-off
  and recovery energies: interpolate within range, then add switching frequency
  times event energy. No extrapolation or universal device inference.
- `energy_balanced_terminal_waveform`: resolved passive-sign multi-terminal
  voltage/current histories plus complete stored-energy history. Exact quadratic
  terminal-power integration minus stored-energy change yields heat. Negative
  dissipated power anywhere in an interval is rejected, including interior
  minima. This bridges resolved circuit samples, not arbitrary device equations.
- `semiconductor_operating_loss_table`: rectangular temperature/voltage/current
  axes and `[temperature][voltage][current]` loss tensors, with trilinear
  interpolation. Maximum 64 nodes per axis and 32,768 Cartesian points; no
  extrapolation. Fixed drive, duty and topology require explicit supplied
  conditions. Conduction is cycle-averaged and each event energy occurs once
  per switching cycle. A table can represent a characterized device family;
  it does not provide universal semiconductor model coverage.

Occurrence/cell weights must sum to one. Feedback uses their normalized weighted
mean temperature; deposition preserves supplied weights. Provenance and energy
nonoverlap are caller declarations, not independently authenticated data.
These sources provide averaged steady heat, not switching circuit transients.

## Validation and remaining scope

On 2026-10-06, 119 focused and adjacent regressions passed with warnings treated
as errors across electrical heating, semiconductor tables, coupled assembly,
tetra electrical/thermal, transient resistive feedback, structured coupling,
retained geometry and PCB binding. The five guided examples executed; the
new first-law case deposited 9.7 W (3.2 W bulk/contact plus 6.5 W device heat),
and the operating-table case deposited 5.2 W (3.2 W plus 2 W). Their thermal
imbalances were below 1e-8 W. Strict schemas, the actual JSON heat worker,
malformed input/resource rejection, multi-affine interpolation and repeated
board ownership were tested. TypeScript and architecture checks passed.
Desktop worker lifecycle checks passed, and the native host library suite
passed 38 tests with one existing live-OS-counter test ignored. New methods
are classified as heavy work on both sides of the desktop process boundary.
An independent numerical review found and fixed negative-heat admission under
subnormal products, one-ULP unequal roots and stored-energy cancellation.
Admission and interval integration now use exact binary-rational coefficients;
published J/W are floats and nonzero underflow is rejected with `numeric_range`.
Those reproducers are permanent tests; bounded re-review found no remaining
material defect. This is software review, not the required human release review.
These are analytical/synthetic software checks, not measured PCB qualification,
a general transient semiconductor solve or proof of installed desktop deployment.

On 2026-10-04, 84 focused tests passed with Python warnings treated as errors:
electrical/thermal tetra kernels, retained assembly admission, coupled analysis,
heating models and existing structured/diode electrothermal regressions. Coverage
includes four-grid manufactured convergence, analytical contact resistance,
conservation, temperature feedback, malformed geometry and conditioning failures,
strict schema validation and the actual JSON worker subprocess.

General PCB CAD volume generation, arbitrary semiconductor subcircuits, transient
coupling, radiation/airflow, independent/measured correlation and desktop coupled
study integration remain open. This is not full-suite or production qualification.
A finite device/model operating-range corpus and knowledgeable numerical review
are required before claiming semiconductor or release qualification.

## Method provenance

### Local board refinement and prescribed air boundaries (2026-10-06)

`solve_layered_board_thermal(design, request)` and the existing
`run_board_thermal` worker accept paired `board.x_edges_mm` and
`board.y_edges_mm`. These are manually controllable, strictly increasing,
full-board physical edges. The finite-volume mesh remains bounded to 8192
planar/131072 volume cells. Each physical stackup row is still one depth cell;
this is not a conforming tetrahedral copper/package mesh. With copper enabled,
`copper_raster_step_mm` is required: fixed sampled occupancy is transferred by
conservative area overlap rather than changed implicitly with solver refinement.
Face conductance uses the two half-cell resistances and actual face area.
Contact/heatsink deposition uses physical rectangle overlap. Existing pad-mode
case-node coupling remains available; it does not reconstruct package bodies.

Optional arrays `board.convection_top_grid_w_m2k`,
`convection_bottom_grid_w_m2k`, `ambient_top_grid_c` and
`ambient_bottom_grid_c` prescribe local surface conditions in x-fast order,
one value per planar cell. Scalar convection fields remain required defaults;
array overrides must leave a positive thermal sink. Steady and backward-Euler
energy balances use each local air temperature. Initial temperature and virtual
heatsink ambient remain scalar `ambient_temperature_c`. For example, a 2-by-1
grid can prescribe `ambient_top_grid_c: [30, 35]` and
`convection_top_grid_w_m2k: [20, 25]`. No airflow or heat-transfer coefficient is
inferred from those inputs. Independent resistance/exponential checks and local
cosine-series refinement tests cover these operators.
Run `python examples/assembly_field/run_local_air_boundary.py` for an original
complete input/result example. Run `python examples/assembly_field/run_fan_system.py`
for synthetic normal/fan-loss passage cases. Both assert conservation and print
JSON; neither silently binds its air state to a PCB or selects convection.

Nonuniform results contain `grid.x_edges_mm`, `y_edges_mm`, `kind: rectilinear`
and no `spacing_mm`. Uniform results retain `spacing_mm`. Heatmaps, board
overlays, cuts, saved-result plots and cell probes use physical cells; visual
smoothing is off by default. This does not constitute installed GUI acceptance.

The source-bound script
`examples/sas_qualification/run_localized_board_reference.py` exported requests,
layer fields, component temperatures and hashed evidence under
`build/sas-localized-replay-20261006-v2`. Original inputs were unchanged. Local
2/1/0.75 mm runs used 1690/3150/4257 planar cells and a fixed 2 mm copper raster.
Peak temperatures were 118.213/119.167/120.024 C with energy residual magnitude
below 4e-12 W. The last peak change is 0.857 K and maximum junction change is
0.505 K: the declared 0.1 K comparison gate **fails**. Assumed square contacts,
losses, plating and h=50 remain diagnostic inputs, not realistic assembly
predictions. Copper feature/face transport, material geometry convergence,
drain-pad selection, package-body paths and installed assembly cooling remain
unqualified. Numerical conservation cannot replace these checks.

Independent review found a cross-axis copper-transfer intermediate that could
exceed the planar cell budget despite bounded inputs. Transfer now chooses the
smaller matrix product order; a regression rejects intermediates exceeding
8192 entries on perpendicular 8192-cell source/target grids. No cell budget was
increased to obtain a result.

### Selective pad paths and uncharacterized board losses

`components[].contact_pad_numbers: ["2"]` selects exact imported pad numbers
only for thermal contact. Copper occupancy still uses all original pads.
Unknown, unnamed, empty, duplicated or internal-only selections fail admission.
Multiple physical surface lands sharing a selected number remain represented.
Polygon clipping preserves admitted contact area on nonuniform grids; curved
boundaries remain polygon approximations, not exact curved CAD geometry.
Selecting a drain pad does not establish an RJC/RCB value or package-body model.

Layered requests additionally accept `board_heat_sources` rows containing
`id`, `component_ref`, `power_w`, and `contact_mode` (`pads` or `square`). Pads
optionally use `contact_pad_numbers`; squares require `contact_size_mm` and
deposit on the top face. These assign all supplied power directly into board
contacts without RJC/RCB. Their result records report board temperature,
`case_temperature_c: null`, `junction_temperature_c: null`, and
`temperature_status: board_only_junction_unsolved`. `components: []` is allowed
with nonempty direct sources; maximum junction temperature is then null.
Combined source count is capped at 256, duplicate source/component assignments
are rejected, and direct contact overlap weights have a cumulative one-million
budget enforced during generation. Plate mode explicitly rejects direct sources.

`examples/sas_qualification/run_sourced_loss_reference.py` maps the supplied
native-board-bound estimated loss ledger using native footprint coordinates,
now retained as `native_footprint_at_mm` separately from legacy pad-centroid `at`.
All six short/tracking sensitivity scenarios executed with 146 sources: eight
selected drain-pad package paths and 138 direct board sources. Their supplied
total losses are 35.75–43.28 W (short) and 14.11–23.42 W (tracking). These are
sensitivity scenarios, not guaranteed lower/upper bounds; individual source
losses change differently. The unlocated auxiliary 2 W remains explicitly
unmapped. Convection, package resistances and loss assumptions are not measured
qualification. Source/result CSVs distinguish unsolved package temperatures;
hashed evidence records inputs, code and omissions. Geometry, mesh, package
and installed cooling qualification are still required.
The six final sensitivity evidence bundles are
`build/sas-sourced-loss-20261006-case0-v2` through `case5-v2`; all six request/result
schemas and committed artifact hashes were checked, each component CSV includes
all 146 sources, and the maximum heat-balance residual magnitude is 4.56e-12 W.
The final short-case replay also lives at
`build/sas-sourced-loss-20261006-final-short-v3` after descriptive-scope admission
was tightened. Read its code hashes before comparing with newer code.

Focused verification passed 146 Python tests with warnings as errors, including
selection, board-only heat, early overlap-budget failure, surface boundaries,
local mesh/Fourier oracles, schemas, CSVs and native-placement preservation.
Desktop panel transport/render, exact-cell viewport/probes, saved-grid admission,
worker supervision, TypeScript, parser, architecture and documentation checks
were also run. Native host library tests passed 38 with one pre-existing
live-OS-counter test ignored. This is not full-suite, Linux, installed GUI,
arbitrary CAD or hardware qualification; concurrent broader checks are separate.
The system CPython 3.11 broad run exposed missing Arrow support. The existing
`requirements-qualification-py311-windows-x64.txt` hashes admitted Arrow 25.0.1
and nanobind 3.0.0 into `build/qualification-py311/site` without changing global
Python; 52 Arrow/package/persistence tests passed with that isolated path.
The ledger records nanobind's Python 3.9 metadata withdrawal; this setup is
Python 3.11, not a compatibility exception or a hash bypass. Full-suite release
qualification still requires its own successful, revision-bound run.
The broader project-runtime run executed 2741 tests on Python 3.12.9 and ended
with one failure, four errors and 15 skips. Follow-up isolated two model-index
tests from the user's unwritable cache and made traversal admission independent
of a real release archive; seven focused tests passed. The owned-descendant
cancellation failure was traced to refused `taskkill /T` followed by parent-only
termination. Windows headless workers now start suspended, enter an owned
kill-on-close Job Object and resume only after assignment. Fourteen headless
tests passed independently, including descendant-handle termination, unrelated
process survival, failed-assignment nonexecution and early-parent-exit cleanup.
POSIX behavior was not executed in this Windows check.

The missing coherent beta report/archive was recovered unchanged from
`build/release-v0.3.7-src/artifacts/releases/beta-0.3.0-beta.1-coherent`;
the retained v0.3.6 copy has identical hashes. Archive SHA-256:
`6e59ed7378f0ab424282fb0d79f63792dfbca686a8b17194b83f224f8822a948`.
The original fixture is restored under `artifacts/releases` locally. All 114
inventory files, offline staging and cleanup passed; both release-verifier
tests passed. Launch smoke remains disabled for this historical fixture and
`production_qualified` remains false. No synthetic replacement or new package
was created. The original broader run was not a green release gate.

The post-fix local Python discovery run passed **2745 tests, zero failures,
zero errors, 15 skips** using `.venv` Python 3.12.9 on Windows 11 build 26200,
NumPy 2.4.2, SciPy 1.17.0, Arrow 25.0.1 and jsonschema 4.25.1. An independent
read-only review found no consequential Windows Job lifecycle/ABI defects.
This is a local working-tree run amid concurrent development, not immutable
release/CI qualification. Skipped tests were not executed; Linux/MPI, clean
package launch, measured correlation and the failed real-board mesh gate above
remain separate requirements. No commit, push or new release package occurred.

### Parallel passage fan operating points

Worker method `solve_fan_system_operating_point` takes exactly
`params: {request: ...}` using
`schemas/fan-system-operating-point-request-v1.schema.json`.
It intersects an explicitly supplied, digest-bound monotone fan P-Q table with
quadratic common/parallel-passage pressure losses, supports series/parallel fan
banks and declared active-fan count, and propagates sensible-air warming through
ordered loads **within each passage**. Separate passages share inlet air, not
successive board outlet temperatures. The original runnable fixture is
`examples/assembly_field/run_fan_system.py`; it covers two/one/zero active fans,
analytical operating-point checks and total/branch energy closure. It is not a
Wakefield characterization or SAS assembly result. Failed fans are explicitly
assumed removed without additional blockage; alternate failure resistance needs
new input. All assigned heat is assumed delivered to that passage.

The [manufacturer fan datasheet](https://wakefieldthermal.com/content/data_sheets/2021_data_sheets/Wakefield-Thermal-DC-Fans-Data-Sheet.pdf)
is contextual primary evidence, not a substituted installed fan curve. Fan
endpoints alone do not define a curve; no curve was invented from them. Reviewed
P-Q data, passage/common pressure losses, blockage, fan-loss behavior and heat
partition remain needed for a physical assembly study. This reduced model does
not compute velocity fields, convection, buoyancy, turbulence, recirculation or
conjugate heat transfer.

The new first-law reduction is independently derived as
`Q = integral(sum(v_port*i_port), dt) - (E_end-E_start)` with passive-sign
ports. For linear samples each product is quadratic; its analytic integral
and endpoint/interior-minimum checks are exact in real arithmetic. Stored
energy is linear between supplied samples. The semiconductor interpolation
uses eight convex corner weights and reproduces multi-affine data; original
polynomial fixtures, endpoints and grid refinement test this invariant.
Neither method reconstructs unresolved switching events or validates supplied
characterization data. Thermal feedback requires temperature-aware device data;
the [official ngspice tutorial](https://ngspice.sourceforge.io/ngspice-electrothermal-tutorial.html)
explains that requirement as context, not as an imported implementation or
independent solver comparison. No external code, model or oracle was copied.

Operators, contact deposition, coupling and loss integration were independently
derived and authored here; no external implementation, netlist or measured data
was copied. Contextual references describe applicability, not code validation:
[ngspice electrothermal tutorial](https://ngspice.sourceforge.io/ngspice-electrothermal-tutorial.html)
and [Infineon switching loss guidance](https://community.infineon.com/t5/Knowledge-Base-Articles/Estimating-SiC-MOSFET-switching-losses-in-applications/ta-p/709113).
