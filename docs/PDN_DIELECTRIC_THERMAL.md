# Dielectric AC loss to temperature

PI02-S03 connects the existing finite-dielectric AC and retained-volume thermal
solvers in one executable workflow. It prepares the shared units, field/source
ownership and energy evidence needed for broader multiphysics work. For
temperature-dependent conductivity, use the separate
[feedback wrapper](PDN_DIELECTRIC_FEEDBACK.md). The original one-way API keeps
fixed electrical material properties and continues within PI/SI priority.

Call `run_pdn_dielectric_thermal(request)` in
`python/spike_core/pdn_dielectric_thermal.py`, or worker method
`run_pdn_dielectric_thermal` with exactly `{request: ...}`. Supply:

- `contract`: `spike/pdn-dielectric-thermal-request/v1`.
- `electrical_request`: the explicit [dielectric AC request](PDN_DIELECTRIC_AC.md).
- `drive`: one `frequency_hz` and `voltages_v`, mapping every signal node to
  `{real, imag}` RMS volts relative to the electrical reference at zero volts.
- `thermal_request`: the existing steady tetrahedral thermal request, with
  supplied thermal materials and boundaries on the identical retained mesh.

The electrical grid must be exactly the one drive frequency. The coupling does
not infer missing signal voltages, combine unrelated tones or sum separate
coherent excitation powers. Both meshes must have identical canonical digests,
including units, cell indices, material identifiers and source-object ownership.
Electrical permittivity/conductivity and thermal conductivity are independently
supplied properties under those matching material IDs. There is no nearest-node
mapping, hidden unit conversion between meshes or automatic material inference.
Pre-existing thermal heat sources must be absent or empty to prevent double
counting. Original requests remain unchanged.

## Conserved electrical-to-thermal transfer

The workflow executes the AC solver internally; a caller cannot substitute a
claimed field result. For signal voltage vector V, combine complex cell basis
fields coherently: `Ecell=sum(Ebasis[:,port] × V[port])`. At angular frequency
ω, the local dissipative tensor is `D=σI+ω tanδ ε`. Average volumetric heat is
`q=Re(Ecell† D Ecell)` in W/m³. RMS phasors require no factor 1/2. Relative
phase and cross terms matter. Cell powers are `volume_m3 × q`; their sum must
match independently computed `Re(V†YV)` at the terminals within stated
relative and floating-point roundoff tolerances. Negative heat is rejected,
not clipped, and reactive power is not turned into heat.

The copied thermal request receives q under exact cell IDs. The existing steady
thermal solver executes using those sources and retains its global heat-balance
evidence. Result temperatures are Kelvin and heat fluxes W/m². Results retain
source/context/mesh digests, per-cell ownership, source density/power maps,
port/volume power comparison, drive and the complete thermal result. Model status
remains experimental with `production_qualified=false` and explicit
`one_way_no_temperature_feedback` coupling mode.

Independent uniform-plate loss and heated-slab references, coherent drive/phase
cases, zero-loss limits and refinement establish bounded acceptance. A uniform
one-metre slab with both ends at T0 and conductivity k obeys
`T(x)=T0+q*x*(1-x)/(2k)` for insulated side walls. Finite-element refinement is
checked against this temperature field, not just heat conservation. The method,
implementation and synthetic fixtures are independently authored SPIKE work.

## Limits and next coupling work

Existing finite electrical-domain, mesh, material, conditioning and thermal
admission limits still apply, together with bounded aggregate request/output
sizes. Cancellation is checked during AC work and around subsolves; the existing
thermal kernel has no internal callback, so callback cancellation cannot
interrupt that individual solve. Failure or cancellation publishes no partial
success result.

This stage does not qualify arbitrary PCB extraction, open-domain EM, fluid flow,
mechanical stress, transient thermal response, temperature-dependent dielectric
properties or measured hardware. New coupling laws and conservative transfer
between different meshes require separate validation. Knowledgeable human
numerical review remains required before release under `CONTRIBUTING.md`.

## Reproducible computed visualization

Run the [original slab example](../examples/pdn_dielectric_thermal/run_slab.py):

```powershell
.venv/Scripts/python.exe examples/pdn_dielectric_thermal/run_slab.py --plot
```

The plot option uses the installed development Matplotlib package; it is not
a new solver dependency. The example writes request/result JSON and
`temperature.png` to `build/pdn-dielectric-thermal-example`. The image displays
actual returned node temperatures and an independently derived slab reference.
The synthetic one-metre cube at 10 V RMS and 1 kHz produces 50.0314 W of heat
and a computed peak of 306.254 K with 300 K end faces. This is a mathematical
example, not measured hardware or a native desktop viewport qualification.

## Stage verification

PI02-S03 is **Done** for its bounded numerical/workflow acceptance. Ten zero-skip
checks passed in the [source-bound execution](validation/parity/PI02-S03.json).
The interpolated P1 temperature's volume-weighted centroid error falls from
0.1118 K at n=2 to 0.02795 K at n=4, demonstrating second-order refinement.
Tests also cover coherent phase/cross terms, amplitude scaling, zero loss,
source ownership, corrupted fields, double counting, resources and cancellation.
Five affected earlier stages were re-executed and their receipts refreshed.

Combined electrical, thermal, schema/worker and evidence regressions passed
121 tests with zero skips in 19.063 s (`build/parity-pi02s03-focused.log`).
Nine documentation checks and the 61-family backlog check passed.

During PI02-S03 verification the global architecture check failed on an unrelated
spread-extrema operation in `app/src/piSearchIntent.ts`, which this stage did
not edit. The later [PI02-S04](PDN_DIELECTRIC_FEEDBACK.md) architecture check passed.
Full release validation remains separate. PI/SI and general multiphysics
capability families remain open.
