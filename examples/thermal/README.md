<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->

# Structured solid-thermal reference example

Start with the [illustrated thermal user guide](../../docs/THERMAL_USER_GUIDE.md)
for board import, input setup, maps, component temperatures, and result review.
Its [Marble v1.4.4 input](marble_v144_plate_thermal.json) uses a pinned public
open-hardware board downloaded separately from Berkeley Lab; the saved
[temperature figure](../../docs/validation/marble-v144-plate-thermal.png) and
[result JSON](../../docs/validation/marble-v144-plate-thermal-result.json) are
exploratory SPIKE output with hypothetical thermal assumptions.

For a real imported board with explicitly assumed object powers and heat paths,
run the [eBrake1 built-in SPIKE thermal example](../../docs/validation/EBRAKE1_OBJECT_THERMAL_20260928.md).
It saves a board-location plot and transient curves. The result remains an
approximate lumped network, not a PCB temperature field.

For a spatial **uniform board-plate approximation** with explicit junction
and case thermal resistances, use the
[eBrake1 board gradient example](../../docs/validation/EBRAKE1_BOARD_THERMAL_20260928.md).
This solves a grid over the imported board bounds; it does not mesh the true
PCB outline or copper stack.

`ebrake1_layered_thermal.json` uses the same pinned board with explicit
dielectric/copper conductivities, via plating, pad contacts, and per-layer
copper geometry controls. The [layered validation record](../../docs/validation/EBRAKE1_LAYERED_THERMAL_20260928.md)
contains an unsmoothed run, a fuzzy/coarse comparison, result JSON, and
temperature/copper figures. Its inputs and results are illustrative and
approximate, not calibrated device or board temperatures.

`ebrake1_layered_virtual_heatsink.json` adds a prescribed mathematical top
heatsink contact with interface and sink-to-ambient resistances. The
[guide](../../docs/THERMAL_USER_GUIDE.md#virtual-heatsink-comparison-on-the-same-fixture)
compares its saved heat flow and junction temperatures with the no-sink run.

`ebrake1_layered_transient.json` adds cell heat capacity and constant-power
transient stepping to the layered board. The [saved run and animation](../../docs/validation/EBRAKE1_LAYERED_TRANSIENT_20260928.md)
show time-step sensitivity, a board temperature gradient over time, and the
limits of the approximate model.

Run the bounded 3-D cell-centred finite-volume example from the repository
root:

```powershell
python scripts/run_structured_solid_thermal.py `
  --request examples/thermal/structured_slab_request.json `
  --result build/structured-slab-result.json
```

The example exercises anisotropic-ready conduction, a prescribed-temperature
face, convection and surface radiation. Its `production_qualified` result flag
is deliberately false: arbitrary CAD meshing, independent-solver and measured
correlation, native Windows/Linux packages and auditable CI remain separate
release gates.

The closed-loop DC resistor example runs through the same development CLI:

```powershell
python scripts/run_structured_solid_thermal.py --request examples/thermal/structured_electrothermal_request.json --result build/structured-electrothermal-result.json
```

It uses the existing MNA circuit engine, an explicit normalized resistor-to-cell
loss map and temperature-dependent resistance. For this example the independent
quadratic balance is `deltaT * (1 + 0.004 * deltaT) = 108`. The returned field
and resistor power must agree with that root. The coupling supports steady DC
resistors and independent sources only; switching semiconductor and transient
electrothermal studies remain unimplemented. This is a development command,
not an OS sandbox or the production job launcher.
# Transient diode/solid-field reference

Run the pulsed current-driven diode example with:

```powershell
python scripts/run_structured_solid_thermal.py --request examples/thermal/transient_diode_field_request.json --result build/transient-diode-field-result.json
```

The example uses the repository's temperature-dependent forward-diode reference
law and an implicit 3D solid-thermal timestep. Every step validates conservative
device heat deposition, nonlinear convergence and thermal energy balance.
This is not general SPICE/transistor coupling, switching-loss simulation or
airflow, and its result explicitly remains non-production-qualified.
