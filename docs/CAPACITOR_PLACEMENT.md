# Supplied-network capacitor placement comparison

The `capacitor_placement.evaluate_capacitor_placement(request)` Python API
compares one added capacitor at each explicitly supplied candidate location.
It returns impedance frequency curves, candidate coordinates and color metrics,
rating diagnostics and a ranking among eligible candidates. Its model status
is **approximate**: the algebra is checked against independent circuit oracles,
but neither the supplied network nor a physical PCB is thereby validated.

The [request schema](../schemas/capacitor-placement-request-v1.schema.json) uses
`spike/capacitor-placement-request/v1`; the returned contract is
`spike/capacitor-placement-result/v1`. Malformed studies raise
`CapacitorPlacementError` with a stable `.code`. A candidate with a resonance,
rating or conditioning failure remains visible and is excluded from ranking.
This module does not modify a PCB, synthesize a converter, or place components.

## Inputs and electrical boundaries

Supply ordered `ports`, strictly increasing positive `frequencies_hz`, and
`z_ohm[frequency][receiving_port][injected_current_port][real, imaginary]`.
The phasor convention is `exp(+j*omega*t)`, with RMS currents and voltages.
Z is the impedance matrix in ohms. All ports share the explicit
`reference_return={occurrence_id, net}`. Every port and candidate must declare
the same `board_occurrence_id`. Source impedances, existing capacitors and
other intended small-signal boundary conditions must already be included in Z.
The reference identity is a caller declaration; the integration layer must
resolve it against the board before execution. This API does not extract a
ground return, mounting inductance, board geometry or terminal connectivity.

Each load declares a distinct `port_id` and positive `current_a_rms`. The
current is the amplitude of an independent sinusoidal ripple excitation at
each sweep frequency. The load list denotes **separate scenarios**, not
simultaneously driven loads or independent harmonics to combine by RMS sum.
It is not a converter's total DC output current. Other external port currents
are zero during that scenario.

Each candidate declares its `id`, `port_id`, `occurrence_id`, `x_mm`, `y_mm`
and a capacitor with effective operating `capacitance_f`, `esr_ohm`, `esl_h`,
`voltage_rating_v`, and `ripple_current_rating_a_rms`. The capacitance must
already reflect any required bias, temperature, tolerance or aging derating.
All values and ratings are explicit; no vendor model or generic grade default
is inferred. Coordinates label the supplied electrical port and do not change
the physics. An interpolated visual gradient between candidate samples is a
display aid, not a solved continuous spatial field.

The request also supplies `dc_voltage_v`, `target_impedance_ohm`, a closed
`frequency_band_hz`, and `provenance={source_id, conditions}`. Provenance is
retained but not authenticated. The requested band must lie within the sweep
and contain at least two supplied samples. All input quantities are SI except
the explicitly named millimeter coordinates.

## Independent derivation

The capacitor's series impedance is

```text
Zcap = ESR + j*(omega*ESL - 1/(omega*C)).
```

Starting from `V=Z*I`, adding a shunt at port c means its outward current is
`Icap=Vc/Zcap`. The original network sees `Iexternal-e_c*Icap`, so

```text
Vc = Z[c,:]*Iexternal - Z[c,c]*Icap
Icap = Z[c,:]*Iexternal / (Z[c,c]+Zcap)
Znew = Z - Z[:,c]*Z[c,:] / (Z[c,c]+Zcap).
```

The multiplication is an outer product, without complex conjugation. Both
transfer directions are preserved; reciprocity is not assumed. The load
driving impedances are the relevant diagonal entries of Znew. At the mounted
port the algebraically identical product form
`Znew[c,c]=Z[c,c]*Zcap/(Z[c,c]+Zcap)` avoids subtracting nearly equal numbers
as the shunt approaches a short circuit. Other near-cancelled updates below
a 1e-12 relative margin are marked `ill_conditioned_update` and not ranked.

The source network must be passive at every supplied frequency: the Hermitian
part `(Z+Z^H)/2` must be positive semidefinite within relative tolerance 1e-10.
This follows from average real power `Re(I^H*Z*I)` being nonnegative for every
current vector. The implementation scales each matrix by its largest entry
magnitude, then uses the existing NumPy Hermitian eigensolver. It neither
projects the matrix onto a passive set nor assumes that finite sampling proves
causality or broadband passivity. A negative loaded driving resistance beyond
tolerance also excludes a candidate. Reciprocity discrepancy is reported
separately and is not a blocking requirement.

The shunt denominator's margin is
`abs(Zcc+Zcap)/max(abs(Zcc),abs(Zcap),1e-300)`. A margin at or below 1e-10
produces `ill_conditioned_shunt_resonance`; the corresponding response is
withheld. No artificial resistance or regularization is added. A singular
sample anywhere in the supplied sweep excludes the whole candidate.

Existing `peec_network.py` owns extraction/MNA assembly; `sparameters.py`
owns S/Z conversion; neither is repeated here. This boundary starts from an
already supplied Z matrix. `si_passives.py` was inspected, but its grade,
leakage and illustrative defaults are not the explicit effective-value
capacitor contract used here. The original series RLC expression is kept
local without importing those defaults or fabricating leakage.

## Scores, curves and ratings

The baseline and every computed candidate return per-frequency complex load
impedances, their magnitudes, maximum impedance and target ratio. The score
`worst_target_ratio` is the maximum of `abs(Zload)/Ztarget` across every load
and supplied sample in the selected band. `color_metric` carries that same
number: lower is better. `improvement_fraction` is `1-candidate/baseline` when
the baseline score is positive; zero-baseline improvement is left undefined.
`peak_frequency_hz` identifies a sampled peak, not a continuous resonance fit.

`ranked_candidate_ids` includes only eligible candidates, ordered by score
and then ID for deterministic ties. `best_candidate_id` means best among
those supplied candidates. `recommended_candidate_id` is populated only when
that best candidate improves the baseline score. It remains null when adding
a capacitor worsens impedance or every candidate is ineligible. Target
compliance is separately reported as `meets_sampled_target`; improvement
does not imply that the target is met.

For each independent load excitation of amplitude A:

```text
Icap = Z[c,load]*A/(Zcc+Zcap)
Vterminal_rms = abs(Icap*Zcap)
Vdielectric_rms = abs(Icap)/(omega*C)
required_voltage_rating = abs(Vdc) + sqrt(2)*max(Vterminal_rms,Vdielectric_rms)
ESR_loss = abs(Icap)^2*ESR.
```

The voltage calculation is a conservative screening envelope retaining both
terminal and internal capacitive voltage magnification. It does not establish
a manufacturer's AC-voltage rating, insulation coordination or allowable
heating. The maximum required voltage and RMS current over **all supplied
samples**, including those outside the scoring band, are compared with the
supplied ratings. Exceeded ratings add `capacitor_voltage_rating` or
`capacitor_ripple_current_rating` issues and exclude the candidate from ranking.
ESR dissipation is reported as the maximum independent-scenario loss; it is
not a thermal solution or a summed broadband loss.

Requests at 800 V or 4000 A are not silently treated as low-voltage cases:
tests verify that inadequate explicit ratings are rejected from selection.
This does not qualify HV, kilowatt, 1 kA or 4 kA hardware. DC busbar capacity,
insulation/clearance, faults, switching transients and converter control
stability require their own models and review.

## Bounded work and verification

Limits are 32 ports, 1024 frequency samples, 256 candidates, 262144 complex
matrix entries and 131072 candidate/frequency/load response points. Shape and
resource checks precede array conversion or candidate evaluation. All inputs
and outputs must be finite. Numerical eigensolver failures and arithmetic
overflow return coded errors instead of partial successful studies.

Run the original regression cases with:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_capacitor_placement -v
```

The tests compare against independent resistor series/parallel formulas and
direct nodal admittance solves of RL networks; check ordered loads and a
nonreciprocal passive matrix; exercise voltage/ripple ratings, same-board return
identity, singular resonance, strict schema, malformed shape/number/resource
admission and a nearly ideal mounted shunt short. A zero-impedance baseline
must not acquire a fabricated improvement.

A nested-frequency regression uses an independently specified parallel L and
series RC circuit. Adding samples nearer its antiresonance materially raises
the measured peak, and all samples agree with the direct circuit formula.
This intentionally demonstrates why a coarse sweep cannot certify continuous
band coverage. There is no unsampled resonance search, interpolation, automatic
mesh convergence or global optimization. Users must refine their supplied
network sweep and candidate locations until the quantities of interest are
stable for their study; the API does not claim that arbitrary input is converged.

## Provenance and validity

The PI setup retains the admitted comparison request and result in the project.
Reopening the tool displays the saved curves and candidate scores directly.
Restore requires a complete matching request snapshot; a mismatched result is
discarded rather than displayed against a different network. Editing an input
marks the previous comparison stale until recalculation succeeds.

Texas Instruments' primary [High-Speed DSP Systems Design Reference Guide,
SPRU889](https://www.ti.com/lit/ug/spru889/spru889.pdf), sections 4.3.1 and
4.3.5-4.3.7, was consulted for capacitor parasitics, impedance-oriented
decoupling and placement principles. Its method context does not establish
validity for an HV or high-current converter. The shunt update, passivity
criterion, rating envelope, implementation and original synthetic oracles
above were independently derived for SPIKE. No third-party implementation,
vendor data, upstream example or test fixture was copied or adapted.

Added material is original Apache-2.0 material. Citations record method
provenance rather than redistribution rights or hardware qualification.
Knowledgeable human numerical review remains required before release.
