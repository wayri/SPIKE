<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->

# Callable conjugate-channel and radiation increments

These new owned in-process numerical implementations are callable now through
the development CLIs below. They do not enable the manager's **general** full-wave
or enclosure airflow/CHT options. No external solver is used by either algorithm.
They are Python/NumPy/SciPy implementations, not new private SPIKES C++ job routes.

## Laminar conjugate channel

```powershell
python scripts/run_structured_solid_thermal.py --request examples/thermal/laminar_channel_cht_request.json --result build/laminar-channel-cht-result.json
```

`spike/laminar-channel-cht/v1` solves nodal plane-channel momentum with no-slip
walls and a prescribed positive pressure gradient. Discrete velocity feeds a
2-D finite-volume conjugate thermal solve over two solid walls and the fluid.
It includes harmonic solid/fluid conductance, axial conduction, upwind energy
transport, viscous dissipation and external temperature/convection boundaries.
No empirical convection coefficient replaces fluid transport at the interface.

The domain is fully developed, steady, incompressible and constant-property;
width only scales the extruded 2-D flow. There are no sidewall-flow corrections,
entrance momentum development, fans, buoyancy, turbulence or arbitrary enclosure
geometry. The Reynolds admission uses continuum Poiseuille flow, not a coarse-grid
underestimate. All admitted cases require Re<=2000, positive temperatures, finite
diagnostics, residual acceptance and pressure-work/thermal-energy closure.

Tests compare the velocity against the parabolic profile, volumetric-flow
second-order convergence, an independent four-cell conjugate matrix, conservative
enthalpy transfer, and axial thermal self-convergence. The latter is not an
independent continuum or measured validation. These are standard conservation
equations implemented originally; method context is available in
[COMSOL's plane-flow reference](https://doc.comsol.com/6.4/doc/com.comsol.help.models.particle.inertial_focusing/inertial_focusing.html)
and [NASA's consistency-verification guidance](https://www.grc.nasa.gov/WWW/wind/valid/tutorial/consistency.html).

## Closed-box radiation postprocessing

```powershell
python scripts/run_huygens_far_field.py --request examples/em/huygens_dipole_request.json --result build/huygens-dipole-result.json
```

`spike/huygens-far-field/v1` consumes collocated complex electric and magnetic
field samples on all six faces of a box. Arrays are `[nu,nv,xyz,real_imag]`,
with tangential axes in ascending coordinate order. Face midpoint positions,
outward normals and areas are derived internally. Peak phasors use `exp(+iwt)`.
The returned vector F obeys `E(r)=F(r_hat)*exp(-ikr)/r`; intensity is W/sr.

Equivalent currents are `J=n cross H`, `M=-n cross E`. Midpoint surface integrals
produce far amplitudes in requested unit directions. No total power or directivity
is inferred from an arbitrary angular sample set. The example uses independently
derived Hertzian dipole near fields—not measured or PCB-solved data.

The box must lie in a homogeneous isotropic lossless exterior, contain every
source/scatterer and avoid PML. Arrays alone cannot prove those conditions or
Maxwell consistency; source-field provenance and containment remain producer
responsibilities. Such restrictions also apply to standard near-to-far methods,
as described in the [Meep interface documentation](https://meep.readthedocs.io/en/master/Python_User_Interface/#near-to-far-field-spectra).
No external source code was copied.

Tests exercise complex amplitude, second-order quadrature convergence, integrated
dipole power/directivity, transversality, translation/phase, malformed fields,
resource bounds and cancellation. This is a postprocessor: it does not solve the
PCB fields, construct ports or qualify a full-wave workflow.

## Remaining integration and release gates

The manager's broad options remain unavailable until admitted geometry/materials,
ports, field sampling and runtime contracts form a complete execution path. Both
results intentionally report `production_qualified=false`. Independent solver
and measured correlation, scalable native/distributed backends, process memory
isolation, clean-machine packaging and private CI remain separate gates. The
CLIs are local development entry points, not sandboxed worker replacements.
