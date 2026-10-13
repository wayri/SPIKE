# Internal PI/SI and retained volume thermal coupling

The experimental `spike/multiboard-volume-electrothermal-request/v1` API couples
the native multiboard linear MNA circuit to the retained tetra thermal field.
Select `thermal_engine: internal` or `calculix`; the latter requires the
separately installed CalculiX runtime. Geometry can come from an admitted Gmsh
mesh or other supplied conforming tetrahedra. This orchestration does not mesh
CAD or extract electrical impedance from board geometry.

Run the original, independently authored examples from the repository root:

```powershell
python -m examples.assembly_field.run_multiboard_volume
python -m unittest tests.python.test_multiboard_volume_electrothermal -v
```

`request('pi')`, `request('si')` and `request(mechanical_part=True)` in the
example module construct reviewable requests. They use synthetic one-metre
slabs, explicit board or enclosure circuit models and explicit thermal contacts;
they are analytical software fixtures, not production board characterization.

## API and ownership

### Desktop and embedded results

In Thermal → retained volume solver setup, prepare the board/part volumes,
then use **PI / SI circuit and volume thermal coupling**. Copy the current
volumes and a saved PI/SI circuit, choose the thermal solver, and use **Show
resistor and volume IDs** to inspect occurrence-scoped identifiers. Supply a
reviewed distribution and temperature law for every resistor. **Prepare coupled
study** admits the case before **Run coupled electrothermal**. Editing the
request invalidates the prior preparation and result; no loss mapping is guessed.

**Thermal part links** converts total resistance in K/W into interface
conductance in W/(m²·K), using `h = 1/(Rth*A)` and actual matched triangle area.
The retained link's resistance and area must agree. Constrained or reused faces,
ambiguous triangles and nonconforming interfaces are rejected. Remesh an
unmatched interface. A package junction-to-ambient rating is not an interface
contact resistance.

**Save coupled study** retains setup and actual results in `.spike`. Reopening
verifies them offline and shows embedded temperatures and resistor losses
without browsing for a result file. Changed physical assembly or topology
withholds stale results. Manifest checks protect concurrent edits and unique
STEP/model members are preserved. Saving the overall project without results
clears the coupled result while retaining its setup.

The worker methods are `prepare_multiboard_volume_electrothermal`,
`run_multiboard_volume_electrothermal`,
`verify_multiboard_volume_electrothermal_result`,
`describe_volume_electrothermal_bindings` and
`prepare_assembly_thermal_contact_model`. Project read/save methods are
`read_volume_electrothermal_in_project` and
`save_volume_electrothermal_in_project`, requiring `project_path` and
`expected_manifest_payload_sha256` (plus `record` on save). MCP exposes numerical
preparation/execution/admission without adding arbitrary file writes.

### Error resolution

| Diagnostic detail | Repair |
| --- | --- |
| `VOLUME_COUPLING_FIELDS`, `LOSS`, or `BINDING` | Review schema fields; map every compiled resistor once with positive weights summing to one. |
| `ASSEMBLY_FIELD_CONTACT` | Review retained endpoints, resistance and area; remove conflicting boundaries or remesh matching interface triangles. |
| `VOLUME_COUPLING_AC` | Use one matching frequency, explicit RMS/peak convention and no unaccounted DC offset. |
| `VOLUME_COUPLING_ENVELOPE` | Supply a justified resistance law over the actual temperature range. |
| `VOLUME_COUPLING_NONCONVERGENCE` | Inspect unrelaxed temperature and power defects, boundaries and feedback strength; review the model and iteration settings. |
| Stale manifest or assembly | Reopen the current project, review changed geometry/links and rerun before saving a result. |

Worker validation failures retain `SPIKE-BE-IPC-E-0001`; project admission
failures retain `SPIKE-BE-PACKAGE-E-0002`, with the diagnostic detail.

`python/spike_core/multiboard_volume_electrothermal.py` owns
`run_multiboard_volume_electrothermal(request, *, cancel_check=None)` and offline
`verify_multiboard_volume_electrothermal_result(request, result)`.
The adjacent setup module admits topology, bindings and limits before execution.
The versioned JSON schema is in `schemas/`.

Required fields are `geometry`, `thermal_problem`, `circuit`, `loss_bindings`,
`iteration` and `loss_accounting: exhaustive_resistor_losses`. The circuit uses
the existing multiboard circuit contract. Both assembly physics identities must
match, including occurrences, placements, thermal contacts and electrical links.
Every occurrence remains electrically distinct until explicitly linked.

Compile the circuit with `compile_multiboard_circuit` to discover resistor IDs.
Bind **every** compiled resistor once in `loss_bindings`, including board and
part resistors, combined link/contact resistors and electrical bond resistors.
Each binding has `element_id`, a normalized `distribution` of positive
`{occurrence_id, cell_id, weight}` entries, and a `temperature_law` containing
`temperature_coefficient_per_k`, `reference_temperature_k` and
`temperature_range_k`. Reference resistance comes from the compiled circuit.
The mapping also defines the temperature sample used in its resistance law.
Different resistor losses may deposit in the same cell; duplicating one
resistor binding or one cell within a distribution is rejected.

`thermal_problem.heat_sources` must be empty: circuit heat is the exhaustive
volumetric load inventory. Prescribed thermal boundaries and retained thermal
contacts are admitted by the shared field binder, including contact area and
thermal resistance consistency. Electrical links represented completely by the
circuit are removed only from the derived thermal-only assembly; the result
retains the original assembly digest and both exact derived thermal inputs.

PI accepts DC operating points. SI accepts one explicit sinusoidal frequency:
use `analysis.points: 1`, equal `start_hz` and `stop_hz`, and `ac_heating` with
matching `frequency_hz` and `phasor_convention: rms` or `peak`. Nonzero DC source
offsets are rejected because this contract does not combine DC and AC heating.
Controlled sources, nonlinear devices and unrepresented rigid-flex links fail.

## Derivation and evidence

This is original SPIKE code and independently constructed test data; no external
implementation was copied, translated or adapted. The transfer follows elementary
Ohm, Joule and energy conservation laws:

* `R(T) = Rref * (1 + alpha * (T - Tref))`, in ohms and kelvin.
* DC loss is the native solver's resistor `V*I`, checked against `I^2*R`.
* Sinusoidal average loss is `|I|^2*R` for RMS phasors and half that for peak.
* Cell power is `sum(weight * loss)` in watts; density is power divided by
  the positive tetra volume in cubic metres.
* Feedback samples are weighted cell-mean nodal temperatures. Resistance must
  remain positive throughout its declared envelope; extrapolation is rejected.

The two-board fixture has 12 V across 6 + 0.1 + 0.2 ohms, so exact electrical
loss is `144/6.3` W. Its AC variant with 1 mH at 1 kHz has RMS total loss
`6.3 / (6.3^2 + (2*pi*1000*0.001)^2)` W for a 1 V RMS source. Tests compare both
phasor conventions, real MNA results, conservative mapped power, thermal balance,
temperature feedback, retained parts/bonds, malformed requests and offline
staleness admission. An optional test executes the installed CalculiX engine.

Each fixed-point iteration solves thermal loading at the current temperature,
then reevaluates the circuit at the returned temperature. Both the **unrelaxed**
temperature defect and relative total absolute cell-power defect must pass.
Reducing relaxation cannot manufacture convergence. Singular circuit solves,
out-of-envelope laws, cancellation and exhausted iteration budgets fail.

## Results and limits

### Component volumes and contact workflow

Use [reviewed component STEP promotion](THERMAL_COMPONENT_SOLIDS.md) to retain
closed package solids with material and mounting transforms. Regenerate the
volume mesh after changing assembly geometry. In the coupled editor, explicitly
rebind the circuit draft to the reviewed current assembly and select packages
that receive their existing board-device losses as thermal-only volumes. Existing
circuit elements are preserved; remove a duplicate package model explicitly.

Discover thermal interfaces in the contact editor, review the candidates, then
apply selected retained links. The backend derives conductance as
`h = 1 / (Rth * area_m2)` from reviewed total K/W resistance and actual matching
mesh triangles. It does not infer resistance from component names or proximity.
Conflicting boundaries, occupied faces and ambiguous links remain blocked.

The temperature viewer offers Celsius/kelvin, individual occurrences, exterior
mesh edges, and bounded interior tetra edges and node samples. Its color scale
uses all retained occurrence temperatures so filtering does not change the
meaning of a color. Saved result identity is checked before display.

Results contain compiled circuit maps, actual native MNA request and result,
per-resistor powers and temperature samples, the actual thermal result,
`thermal_geometry`, `thermal_problem`, applied and feedback cell powers,
loss balance, iteration history and request/result digests. The difference
between final feedback powers and the actual thermal loads is retained.
Offline admission verifies identity, exact derived thermal inputs, mapped
loss coverage and convergence evidence without invoking either solver. It
reassembles the native sparse circuit equations and checks `A*x-b` using saved
voltages and branch currents, then derives every element current/power and AC
magnitude/phase again. This rejects numerically inconsistent electrical fields
even when the containing digest was recomputed. The derived thermal geometry is
normalized to JSON arrays so saving and reopening preserve the same identity.
Digests provide integrity/staleness checking, not authenticity or physical proof.

The model is steady averaged heat, with ideal independent sources and ideal
reactive elements. It does not infer source-device losses, switching waveforms,
nonlinear device dissipation, full-wave coupling, thermal transients or contact
pressure. Link conductor/contact resistance currently compiles to one resistor;
its explicit weights and temperature law describe that combined loss.
Mesh error, supplied resistor accuracy and fixed-point conditioning require
separate evaluation. Very strong feedback may not converge; a passed iteration
tolerance is not a physical or spatial error bound. CalculiX NT output has
finite precision and does not report global thermal balance through this adapter.
All results remain experimental and not production qualified; numerical changes
require knowledgeable human review before release.
