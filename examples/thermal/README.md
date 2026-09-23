<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->

# Structured solid-thermal reference example

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
