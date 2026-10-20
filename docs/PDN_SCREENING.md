# PDN Target and Decoupling Screening

[Run SI and PI now](RUN_SI_PI_NOW.md) includes saved RC/RLC requests and a
tested CLI path: `python -m python.spike_core.cli --output result.json
pdn-network request.json`. This solves the explicit AC/load-transient model
through the same worker as the desktop; no board parasitics are inferred.

The [passive sampled reduction workflow](PDN_ADMITTANCE_REDUCTION.md) admits
explicit auxiliary-port loads and floating ports while retaining selected PDN
ports. It preserves the exact grid and reference; no causal fitting is implied.

For explicitly meshed dielectric conductivity and AC loss, use the separate
[finite-dielectric admittance workflow](PDN_DIELECTRIC_AC.md). It solves complex
fields and returns finite-band samples; it does not infer capacitors for the
frequency-invariant transient model.

Source additions for explicit AC/filter and load-spike execution are described
in [the new workflow](#explicit-ac-pdn-and-filter-workflow). Existing extracted
board PI validity limits below remain unchanged.

The [PI04-S01 consistency correction](PI_SI_PARITY_EXECUTION.md#pi04-s01-transient-consistency)
preserves passive energy while correcting finite-rise inductive-cutset voltages.
Initial/interior PWL corners use right-sided voltage observations; the final
endpoint uses the left derivative. Single-load, supplied linear-network scope
and unsupported arbitrary initial stored energy remain explicit for that stage.
The additive [simultaneous-load form](PDN_SIMULTANEOUS_LOADS.md) supplies
independent named-port PWL waveforms with a common horizon and shared-return
voltage/energy accounting. It retains the legacy single-load form.

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

The desktop candidate review is a display of the returned `spike/pdn-review/v1`
values. It shows the reviewed target, source worst impedance and violation count,
candidate C/ESR/ESL/count and mounting values, placement model, assumptions,
status, and before/after worst impedance. It requires the review to be bound to
the active source analysis ID. Saved reviews without that binding must be rerun;
the review envelope itself does not currently carry the source ID. The display
rejects candidate rows with missing/nonfinite model or response values, source
ID mismatch, or a frequency grid different from the source sweep. The original
raw review remains available for diagnosis.

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

## Explicit AC PDN and filter workflow

The source desktop Power Tree has **AC PDN / CM-DM filters**. This separate
workbench edits `spike/pdn-network-request/v1` with named electrical nodes,
an explicit reference, supplied component values/provenance, ports, frequency
points and an optional finite-rise PWL current pulse. Reference suggestions
default to ground-like board net names, but the user can select another board
net or edit the reference identity in the request. A suggestion is not proof
that physical copper, grounds on different boards, or return paths are connected.

1. Open Power Tree, then the AC PDN/filter tool. The initial RC model is an
   independently authored mathematical example, not extraction of the board.
2. Select/review ground and name the rail/layer/connector nodes. Connect series
   and shunt R/L/C explicitly. Supply source output resistance/inductance;
   an ideal regulator response is never guessed.
3. Use the DM-choke, coupled CM-choke, net-to-ground C or series-capacitor
   templates. Zero values are placeholders that must be edited before running.
   A CM choke requires both winding endpoint pairs, positive L, winding R,
   coupling below one and explicit dot polarity. Define winding/self/plane
   parasitic capacitors as separate elements rather than hiding them in a name.
4. Add decaps with their C, ESR and ESL. Component values are user-definable at
   pre-simulation time; no part number is required. They must represent the
   intended bias, temperature, frequency and small-signal operating conditions.
5. Enter current-versus-time points and output times. A pulse starts at zero
   perturbation, includes finite rise/fall and can return to zero. Requested
Output and PWL events are included exactly in the integration grid.
6. **Save AC setup to tree** retains the request in `piTopology.acPdnRequest`.
   Run, inspect driving-point and named-node transfer impedance, then port/net
   voltage deviations during the load spike. Existing immutable project history
   carries the whole tree. Export setup and results independently when needed.

Editing setup hides stale curves. Stop discards late responses; the worker
never publishes a partially completed network solve. Browser preview is
authoring-only; actual desktop/worker execution is required for calculations.
The source workbench has JSON authoring and templates, not an automatic
schematic/PCB-to-complete-filter compiler. Headless render/bridge tests and a
frontend build do not establish installed native GUI or narrow-window visual
acceptance; those checks remain separate from numerical acceptance.

### Capacitance sources and field extraction

`pdn_shunt_capacitance.normalize_shunt_capacitance` admits explicitly referenced
lumped capacitor data or a reduced Maxwell matrix. `pdn_capacitor_elements`
requires the expected current context digest before attaching a source.
For `Q=C V`, pair capacitances are `c_ij=-C_ij`; capacitance to the removed
explicit ground is `c_i0=sum_j C_ij`, not `C_ii`. Every mutual edge and conductor
state is retained. Positive diagonal values alone cannot justify a passive
network, correct ground connection or an accuracy claim.

The existing planar unique-area surrogate can be used through
`estimate_geometry_shunts` with typed design/spec/branches and digest-bound
mesh evidence. It remains approximate and rejects incomplete source/return
coverage, ambiguous geometry, selected vias and unsupported dielectric loss.
It cannot replace a qualified electrostatic extractor for arbitrary boards.

`extract_pdn_electrostatic` is an actual sparse P1 field solver for an explicitly
retained conforming tetrahedral dielectric volume. Its request provides scalar
or SPD-tensor permittivity in F/m, named electrode mesh-vertex groups, one named
ground electrode and an explicit finite **insulating** outer boundary. It uses
unit-potential basis solutions, summed electrode reaction charges, and an
independently integrated dielectric field-energy matrix. Output includes the
full reduced Maxwell C, basis potentials/charges, terminal/mesh lineage,
input/context digests, residual, condition, reciprocity and energy checks.
No negative matrix mode is clipped and no diagonal-only substitute is returned.

The workbench's **Extract from retained dielectric mesh** accepts this request
as JSON, runs the actual field solver, verifies that its reference matches the
selected PDN reference, and attaches all field-derived capacitor edges. Duplicate
IDs fail attachment rather than silently doubling capacitance. The outer
boundary is not open/infinite, conductor sheets are zero-thickness and selected
equipotential, and geometry-specific/fringing refinement remains required.
This is not automatic arbitrary-PCB dielectric meshing or conductor recognition.

### AC and load-spike model

`pdn_network.evaluate_pdn_network` uses the same real descriptor equations for
both studies: `E x' + A x = b`, where x contains node voltages and coil currents.
Capacitance and signed coupled inductance form symmetric nonnegative storage;
R forms dissipation and branch incidence forms the power-conjugate skew part.
AC solves `(A+j omega E) X = B`, with multiport `Z=B^T X`. Node transfer
impedance is the original node rows of X, not a field inferred in the frontend.
CM ports split total excitation current equally and observe mean voltage; DM
ports inject opposite currents and observe differential voltage. For equal
windings, `Zdm=2[R+j omega(L-M)]` and `Zcm=[R+j omega(L+M)]/2`.

The transient is a small-signal linear passive solve, not an absolute rail
voltage or nonlinear regulator simulation. Trapezoidal integration checks
stored `x^T E x/2`, midpoint input work and physical dissipation at every step.
Compensated cumulative work/dissipation and the actual energy-flow scale
avoid an ill-defined relative-to-zero test after a pulse fully decays.
Equilibrated matrix conditioning and unscaled backward errors reject ill-posed
responses. Constant R/L/C does not model ferrite dispersion, saturation,
semiconductor nonlinearities, dielectric dispersion or VRM feedback loops.
The existing copper/PEEC solver's separate validity limits still apply.

API limits are 64 original nodes, 128 elements, 16 ports, 512 frequencies,
20,000 steps and 256 total unknowns, further restricted by a 100-million
`(frequency_count+steps)*unknowns^3` dense-work budget. JSON requests/results
are bounded to 8/16 MiB. Numerical loops poll cancellation; desktop operations
run under the existing owned heavy-worker supervision. `validate_pdn_network`
performs structural/resource admission only, not a solvability or accuracy claim.

### Series capacitor legs and voltage ratings

Model each capacitor and the intermediate nodes explicitly. For linear ideal
capacitors with zero initial charge, `Ceq=1/sum(1/Ci)` and instantaneous
capacitive voltage fractions are `(1/Ci)/sum(1/Cj)`. The separate
`review_series_capacitor_leg` request admits total voltage, individual C,
tolerance, rated voltage and explicit leakage/balancing resistances.
It computes each device's worst capacitive tolerance case, not a single
simultaneously attainable sum of worst-case voltages.

Two 10 uF, 6.3 V capacitors with +/-20% tolerance on 12 V can each see 7.2 V
in its own worst capacitive-sharing case. The 12.6 V nameplate sum is therefore
not a safe voltage rating. Long-term DC sharing depends on leakage; unknown
leakage is reported unknown even if a balancing resistor is supplied. Complete
supplied leakage/balancing values permit nominal modeled DC division, not
certified limits over temperature, bias, aging and tolerances. Fast-edge sharing
and slow DC sharing are different tests. Automatic voltage uprating is never
permitted by this helper. Match the review's IDs, total rail voltage and models
to the actual circuit; the review example is not automatically linked to a bank.

### Reproduce numerical evidence

```powershell
.venv/Scripts/python.exe examples/converter/run_pdn_network_validation.py --output-dir build/pdn-network-new
.venv/Scripts/python.exe -m unittest tests.python.test_pdn_network tests.python.test_pdn_shunt_capacitance tests.python.test_pdn_electrostatic tests.python.test_pdn_network_worker -v
cd app
node scripts/test-pdn-network-panel.mjs
```

Use a fresh output directory. `build/pdn-network-validation-20261012-v2`
retains four actual AC/pulse solves (RC, DM filter, series caps, CM/DM filter),
field extraction and capacitor-rating examples, exact inputs/results, hashes
and source/machine provenance. Their maximum AC backward error is 1.12e-16;
maximum transient absolute energy error is 2.74e-19 J. Analytical tests cover
RC finite-rise convolution, series RLC, signed CM/DM coupling, Maxwell energy
and floating-conductor reduction, unit conversion, layered dielectric, plate
refinements, cancellation/resources and corrupted-solver rejection.

The finite ideal plate matches epsilon*A/d across 1/2/3 refinements within
1.33e-15 relative error. It is an exact affine witness, not a fringing or
arbitrary-PCB convergence study. All derivations, code and synthetic fixtures
are independently authored. No external source implementation or example
dataset was copied; existing NumPy/SciPy dependencies retain their licenses.
Knowledgeable human numerical review, geometry-specific mesh/time convergence,
independent/measured board correlation, general board-to-port compilation and
cross-platform/deployed-GUI acceptance remain necessary for sign-off claims.

Local development checks on 2026-10-13 passed 46 affected Python tests,
including exhaustive tolerance corners for an asymmetric three-capacitor leg
and balancing-with-unknown-leakage rejection of a DC-sharing claim. Independent
read-only review confirmed the sharing equations under their stated assumptions.
The panel's actual-backend/admission checks, TypeScript build, parser and
power-tree regressions, and architecture/control checks passed. Rust library
checks passed 54 tests with one ignored. Native visual inspection could not
complete because app-access approval timed out; these checks do not establish
installed-package or cross-platform qualification.

The broader Python run completed 3,548 tests with four errors and 48 skips;
all four errors were missing analytic sine-source exports in the stale local
`build-peec-native/spikes_c_api.dll`, not PDN assertion failures. Rebuilding
the current `spikes_c_api` target in the MSVC x64 developer environment resolved
them: the 11 sine-source tests passed (one skip), and the broader 496-test
SPIKES integration subset passed (24 skips). The full 3,548-test suite was not
rerun after that rebuild, so this is not a claim of one green full-suite run.
All 26 retained-volume/PWM electrothermal consumer checks also passed against
the rebuilt DLL with the real native integration environment enabled.
