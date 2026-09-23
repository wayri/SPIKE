# PDN Target and Decoupling Screening

SPIKE reviews a solver-produced driving-point impedance sweep against a
positive target impedance. It reports violating points, resonance and
anti-resonance extrema, worst frequency, and logarithmic target-excess area.
Decoupling candidates are evaluated without changing or inferring geometry.

## Placement Models

### Direct port shunt

The capacitor bank is placed directly across the reviewed port:

```text
Zloaded = Zboard || Zcapacitor
```

This is useful for checking component value, ESR, ESL, and count. It is always
`Approximate` for placement because no mounting or plane path is represented.

### Explicit series connection path

Mounting resistance and inductance, plus an optional frequency-dependent
spreading-impedance sweep, are placed in series with the capacitor bank before
the parallel reduction. These are effective bank-level path values. This mode
can compare reviewed lumped mounting alternatives, but it still treats the
path as a branch at the original port and remains `Approximate`.

### Multiport impedance loading

For a location-specific candidate, the source extractor supplies the original
driving point `Z00`, candidate local driving point `Zcc`, and forward/reverse
transfer impedances `Z0c` and `Zc0`. SPIKE applies the exact linear two-port
load reduction at every frequency:

```text
Zloaded = Z00 - (Z0c * Zc0) / (Zcc + Zcapacitor + Zmount)
```

The candidate must carry a source result ID, reviewed endpoints, a model
status, and a frequency grid identical to the reviewed sweep. SPIKE does not
silently interpolate location data. Missing provenance, mismatched grids,
singular reductions, and non-passive loaded responses are rejected with
`SPIKE-BE-PI-E-0100`.

The reduction can inherit `Validated` only when the source driving-point and
candidate multiport data are validated and reverse transfer is explicit or
reciprocity is explicitly declared. It does not promote an approximate PEEC
or capacitance extraction.

### Native PEEC candidate extraction

`spike.peec_2_5d` can now emit `spike/pdn-multiport/v1` when an AC analysis
contains explicit source/load terminals and `options.pdn_candidate_ports`.
The adapter assembles one PEEC MNA system per frequency and solves all
candidate excitations as a bounded multi-right-hand-side problem. The result
contains the observation driving-point impedance, each candidate local and
forward/reverse transfer impedance, the full Z matrix, residuals, sampled
condition numbers, reciprocity error, and a passivity indicator.

```json
{
  "options": {
    "max_pdn_candidate_ports": 16,
    "pdn_candidate_ports": [
      {
        "id": "C17-placement-A",
        "net": "VCC",
        "position_mm": [42.5, 18.25],
        "layer": "F.Cu",
        "endpoint_reviewed": true
      }
    ]
  }
}
```

The default limit is 16 candidate ports per net and the hard limit is 64.
Candidate coordinates must map to the source-connected copper component. The
source terminal is used as an ideal common reference, so the extraction is
always `Approximate`: it does not yet include extracted return-path impedance,
power/ground differential ports, or a multiconductor capacitance matrix.
`endpoint_reviewed` records operator review but cannot promote validity.

Canonical diagnostics are:

- `SPIKE-BE-PI-W-0101`: bounded ideal-reference approximation.
- `SPIKE-BE-PI-E-0102`: invalid candidate contract or terminal/mesh mapping.
- `SPIKE-BE-PI-P-0103`: invalid or exceeded candidate resource limit.

## Candidate File

The canonical candidate set is `spike/pdn-candidate-set/v1`, described by
`schemas/pdn-candidate-set-v1.schema.json`. The CLI also accepts a single
candidate object or raw array for convenience:

```text
spike --output pdn-review.json pdn-review ac-result.json \
  --target-ohm 0.05 --net VCC \
  --candidate-file candidate-locations.json
```

The compact `--candidate ID,C_F,ESR_OHM,ESL_H[,COUNT]` option remains a
direct-port screen. A versioned wrapper with an unknown contract is rejected,
and a single review is bounded to 4,096 candidates.

## Remaining Validation Gates

The permanent solver corpus includes
`pdn_two_port_capacitor_loading_circuit_reference`. It constructs a passive
two-node network, derives the unloaded two-port Z parameters, applies SPIKE's
candidate loading path, and compares every result point with an independent
nodal re-solve of the loaded network. This validates the implemented circuit
reduction and frequency-grid handling. It does not validate PCB multiport
extraction, capacitor vendor models, or physical placement accuracy. Separate
unit coverage checks the native shared-reference matrix against a closed-form
resistor network and exercises its PEEC result contract; those checks do not
promote the PCB extraction beyond `Approximate`.

- Correlate the emitted PCB multiport Z matrices for real candidate pads and
  observation ports against an independent field/network extractor.
- Include capacitor bias, temperature, tolerance, aging, and vendor model
  provenance.
- Validate package/mounting extraction, plane spreading, and via transitions.
- Confirm the predicted ranking by rerunning the extracted network and by
  measurement on benchmark boards.
- Couple regulator output impedance/control-loop models through the SPICE
  workspace where required.

Until those gates pass, this feature is engineering screening rather than a
claim of globally optimal physical placement.
