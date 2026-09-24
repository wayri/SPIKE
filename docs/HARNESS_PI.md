# Connector authoring and native harness DC PI

## Workflow

1. Import boards and orient their occurrences through the existing
   [assembly and FreeCAD exchange](MULTIBOARD_HARNESS_ASSEMBLIES.md). Board
   occurrence IDs remain distinct even when the electrical design is reused.
2. Open **Solve > PI > Harness PI**. Create or edit the project harness document.
   The assembly editor also offers pin-pair tables and bulk mappings.
3. Add connectors and physical pin IDs. Select a connector pair and enter
   `1=5`, `2=6` on separate lines (CSV/tab pairs are also accepted). Duplicate
   source or destination pins are rejected; crossovers require explicit mapping.
4. Enter wire resistance explicitly, or retain a complete resistivity/length/area
   model through JSON. Geometry does not imply an electrical return connection.
5. Select an explicit ground pin, voltage sources and current loads. Every
   terminal has positive and negative/return endpoints. Add mated pin contacts
   as separate positive-resistance elements, including return contacts.
6. Run **Harness PI DC**. Review endpoint voltages, wire/contact currents and
   losses. Changing the harness or setup marks previous displayed results stale.
   Stop targets this operation ID through the shared worker lifecycle.
7. Save the project to retain the harness and its setup in
   `extensions["spike.harness-pi"]`. Result display is currently session-local;
   use CLI output to retain a standalone result record.

## Connector defaults

The authoring catalog includes generic Berg/2.54 mm headers, jumpers, D-sub,
XT power, Datamate, Gecko, Micro-D, power and signal classes. These are editable
starting estimates, not manufacturer-qualified electrical or mechanical models.
Stored pin width/height does not infer pin shape, mating geometry, current rating,
contact resistance, inductance or capacitance. Connector metadata is not silently
stamped into the circuit: each simulated mated contact is explicit.

Use the exact part number and its current datasheet for engineering review.
[Harwin's datasheet index](https://www.harwin.com/resources/product-datasheets)
distinguishes signal and mixed-power families; one family label cannot establish
the resistance or current rating of every variant. No upstream model/code was
copied into the catalog.

## CLI and contract

```powershell
.venv/Scripts/python.exe -m python.spike_core.cli --output result.json harness-pi --request request.json
```

Worker: `run_harness_pi`, parameters `{ "request": ... }`.
Request: `spike/harness-pi-request/v1`, containing the existing `spike/harness/v1`
document, `ground`, `terminals`, `contacts` and optional resource limits.
Schemas: `harness-pi-request-v1.schema.json`, `harness-pi-result-v1.schema.json`.
Endpoints are `{ "connector": "J1", "pin": "1" }` or `{ "splice": "S1" }`.
Sources use `type: voltage_source` with value in volts; loads use
`type: current_load` with value in amperes flowing positive to negative.

The adapter composes the existing native MNA DC kernel. Ohmic losses use I²R;
capacitors are open in DC, inductors impose zero DC voltage, explicit shunt
conductance becomes resistance. A current source is not treated as a conductive
return. Floating circuits, unknown pins, duplicate IDs and unresolved resistances
fail. Bounds: 8 MiB request, 1024 nodes, 4096 elements, with tighter user limits.
Cancellation discards outputs. The desktop route requires a compatible local
worker and solver.

## Validation and limitations

The independently authored 12 V/2 A loop fixture uses 0.1/0.2 ohm wires and
0.01/0.02 ohm contacts: KVL predicts 11.34 V at the load, I²R predicts 1.2 W wire
loss and 0.12 W contact loss. Regression tests also check power balance, missing
returns, invalid pins, DC reactive limits, conflicting sources, cancellation,
and worker/CLI parity. This is circuit validation, not board correlation.

`scripts/validate_marble_harness_pi.py` exercises two rotated occurrences of the
already retained [Berkeley Lab Marble](https://github.com/BerkeleyLab/Marble)
v1.4.4 source. Evidence in `artifacts/beta-validation-20260920/marble-harness-pi.json`
records the board hash, J11 pins 1/10, route and a synthetic 11.6 V loop result.
The selected pins are identity-test terminals, not a recommended physical power
connection. No Marble pin rating, board copper or measured response is validated.
No additional upstream source or dataset was copied by this increment.

[Kikakuka](https://github.com/buganini/Kikakuka) was reviewed at the user-facing
workflow level as the requested multiple-PCB/FreeCAD reference. Its implementation
was not copied. SPIKE reuses its own FreeCAD exchange and placement feedback.

This is **experimental lumped DC**, not full multiboard PI. Coupled PCB copper
models, arbitrary AC/transient board networks, SI connector/launch models,
mutual coupling, automatic pin-rating checks and assembly-wide field results
remain pending. Future SI adapters can reuse endpoint identity, board bindings,
wire models and explicit references, but must supply their own qualified
frequency-dependent/distributed models. Numerical release review is required.

Final integration checks: 1808 Python tests passed (nine skipped), 38 Rust tests
passed (one ignored), connector/pin preservation tests, rendered PI-panel failure
and recovery tests, project round-trip, TypeScript, architecture and the
production frontend build passed before subsequent concurrent viewport edits.
A final TypeScript recheck then reported unrelated `ProbeResultRow.probe` uses
and an invalid jump in `resultSurfaceInterpolation.ts`; these were referred to
the owning task and currently block a fresh release build. These checks do not replace desktop interaction
or measured coupled-board validation. No installer was generated or installed.
