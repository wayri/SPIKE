# Retained EM independent reference

This original validation study covers the two finite conducting plates and
closed enclosure in `tests/python/test_assembly_em.py`. It does not qualify the
enclosed Arduino assembly, routed PCBs, conductor losses or radiated emissions.
Production qualification remains false. Numerical human review remains required.

## Independent reference and assumptions

`scripts/validate_retained_assembly_em.py` independently solves the electrostatic
Laplace equation in the actual 14 mm cubical air cavity. The finite electrodes
occupy x,y = 0..10 mm and z = 0..1 mm / 4..5 mm. Cavity boundaries are at
-2 and 12 mm. The enclosure and plates are equipotential perfect conductors for
this reference; no infinite-plate approximation is used. Dynamic inductance,
radiation and finite-conductivity dissipation are outside the reference model.

Derivation: vacuum electric energy on a uniform grid is one half the sum over
neighbouring nodes of `epsilon_0*h*(V_i-V_j)^2`. Stationarity at each free node
gives the seven-point discrete Laplace equation. A conductor's outward electric
displacement flux is the sum of `epsilon_0*h*(V_conductor-V_neighbour)` over its
boundary grid edges, in coulombs. Two unit-voltage solves form the Maxwell
capacitance matrix `Q = C V`. With the cage as potential gauge, set the electrode
voltage difference to 1 V and solve their common potential from zero total
electrode charge. This models a floating two-terminal source transferring charge
between the electrodes; it does not ground either electrode to the cage.

The sparse positive-definite linear systems use installed SciPy conjugate
gradient with relative residual below 1e-10. Grounded walls remove the constant
potential nullspace. Corner charge singularities limit spatial convergence;
linear solver residual alone is not a spatial error estimate. Manufactured
harmonic polynomial, reciprocity, charge conservation and positive matrix
eigenvalue tests exercise the independently written reference.

The reference uses the same physical dimensions as the input fixture but does
not call the retained geometry compiler, field solver, or OpenEMS mesh builder.
It is a separate static discretization, not a second execution of OpenEMS.
SciPy is the linear algebra library, not an independent commercial EM engine.

## Port and field comparison

For this one-port 50 ohm study, convert the executed reflection coefficient by
`Z = 50*(1+S11)/(1-S11)`, `Y = 1/Z`, `C_effective = Im(Y)/(2*pi*f)`.
The 250 MHz sample is the static comparison: cavity extent/wavelength is about
0.0117. A small dynamic correction is still expected. Real impedance is not a
qualified loss prediction and can show small negative numerical residuals.

`scripts/validate_retained_em_field_scaling.py` calls the installed public
`openEMS.utilities.DFT_time2freq` API on known signals and actual port histories.
Five constant unit samples with dt=0.25 s give pulse DFT 2.5 s at zero frequency;
doubling dt gives 5 s, while periodic mode gives 2. This establishes the installed
pulse convention `2*dt*sum(value*exp(-j*omega*t))` empirically without reading or
copying external implementation. Port voltage pulse spectra therefore carry
V*s. Current spectra carry A*s. `(U-50*I)/(U+50*I)` reproduces the retained S11.

The actual E HDF5 samples divided by the complex total-port voltage spectrum
are compared with `-grad(V)` from the independent 1 V electrostatic solution at
the same physical coordinates. Selected points lie at least 0.5 mm inside the
air gap and 2 mm inside the plate footprint. This checks vector direction,
phase and amplitude, not just a field maximum. The legacy installed HDF5 data
is interpreted as component,z,y,x; positions come from its recorded metre axes.
Dividing by incident spectrum `(U+50*I)/2` instead gives the field for 1 V peak
incident excitation. The check also verifies every embedded preview E/H sample
against its recorded coordinate and independently computed incident spectrum.
That H check verifies normalization and data transfer; it does not supply an
independent magnetic-field accuracy oracle.

## Gates and reproducibility

The declared fixture gates are: last static refinement change <=1%; maximum
complex S11 change under longer duration <=1e-4 and under doubled air margin
<=1e-4; finest-mesh 250 MHz capacitance within 5% of the finest static reference;
coarse-to-fine capacitance change <=7.5%. The latter is a coarse discretization
diagnostic, not a continuum error bound. The script asserts the gates and saves
actual values in `validation-summary.json`.

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_retained_em_reference -v
.venv/Scripts/python.exe scripts/validate_retained_assembly_em.py --output "$env:TEMP/spike-new-independent-em"
.venv/Scripts/python.exe scripts/validate_retained_em_field_scaling.py "$env:TEMP/spike-new-independent-em/spatial"
```

`--resume` retains completed cases and places one retry of an interrupted case
in a separate directory. Failed/interrupted artifacts remain evidence.
The 2026-10-11 run is an unbundled local record named
`retained-assembly-em-independent-20261011`.
The duration variant doubles the 40,000 timestep cap and tightens energy decay
from 1e-6 to 1e-9. It reaches the 80,000 step cap at an approximately -81.74 dB
energy floor, missing the requested -90 dB criterion. It must not be reported
as energy-decay convergence. Its stable response is duration evidence only.
The PML and spatial runs retain the practical 1e-6 decay criterion.

### Executed evidence on 2026-10-11

| Check | Measured result | Stated gate |
| --- | --- | --- |
| Independent C, 0.5 / 0.25 / 0.167 mm | 0.779461 / 0.761948 / 0.757260 pF | last change <=1% |
| Last independent C change | 0.6190% | <=1% |
| OpenEMS C at 250 MHz, 1 / 0.5 mm | 0.817225 / 0.774850 pF | fine/reference error <=5% |
| Fine C/reference discrepancy | 2.3227% | <=5% |
| Coarse/fine C change | 5.4657% | <=7.5% |
| Coarse duration, max complex S11 change | 8.6011e-6 | <=1e-4 |
| Air margin 6 to 12 mm, max complex S11 change | 3.5320e-6 | <=1e-4 |
| Fine air-gap complex E-vector error | 4.9639% maximum, 4.5593% RMS | maximum <=5% |
| Fine preview/raw transfer, E and H | zero error across 4913 samples each | <=2e-6 relative |
| Supplementary fine duration, max complex S11 change | 1.2064e-4 | <=1e-3 |
| Time-refined fine C at 250 MHz | 0.775124 pF, 2.3590% reference discrepancy | <=5% |
| Time-refined fine E-vector error | 4.9133% maximum, 4.5038% RMS | maximum <=5% |

The field check is a scoped correlation, not field convergence: coarse maximum
error was 4.7011%, so the vector discrepancy does not decrease with this spatial
refinement. The fine default run stopped at 15,500 steps and -62.19 dB. A
supplementary fine-duration case uses a 40,000 timestep cap and 1e-8 decay with
a predeclared maximum complex S11 change gate of 1e-3 to check that stopping
uncertainty. It stopped at 17,000 steps and -86.36 dB in 163.10 seconds, meeting
the requested -80 dB threshold. The large relative changes of the small real
impedance component confirm that dissipative loss is not resolved. Capacitance
and complex reflection remain within the declared study gates. Actual metrics
are retained in `validation-summary.json`; per-point field evidence is in each
completed case's `field-reference.json`.

Small calculated real impedances include negative numerical residuals. Neither
these values nor the field agreement qualify power dissipation or conductor
losses. The study envelopes `pml-distance-retry/study.json` and
`spatial/study.json` and `spatial-duration/study.json` preserve actual
requests/results for loading saved fields. The latter is the preferred final
fixture with the stronger decay criterion. All three independent-reference
unit tests passed on 2026-10-11.

## Method provenance

All reference code, fixture interpretation, derivations, tests and prose are
original SPIKE material under Apache-2.0. No external implementation or example
was copied, adapted or inspected. Authoritative method/API references:

- [COMSOL electrostatic theory](https://www.comsol.com/multiphysics/electrostatics-theory)
  for potential, floating conductors and field energy.
- [COMSOL capacitance matrix discussion](https://www.comsol.com/blogs/how-to-calculate-a-capacitance-matrix-in-comsol-multiphysics/)
  for independent unit-terminal solves and Maxwell capacitance.
- [OpenEMS ports](https://docs.openems.de/en/latest/concepts/ports.html)
  for incident/reflected port spectra.
- [OpenEMS utilities API](https://docs.openems.de/en/latest/python/openEMS/utilities.html)
  for `DFT_time2freq`; installed 0.0.36 numerical behaviour is checked explicitly.
- [OpenEMS field dumps](https://docs.openems.de/en/latest/concepts/dump.html)
  for frequency-domain dumps and cell interpolation.
