# Simultaneous supplied PDN loads

PI04-S02 extends the explicit passive PDN workflow with independently supplied
finite-rise PWL loads at named ports. It preserves the single-load request and
result. Use the desktop PDN JSON editor, worker methods `validate_pdn_network`
and `evaluate_pdn_network`, or Python API. Existing panel plots show returned
port and named-node voltage deviations for either request form.

The additive `load_transient` form is:

```json
{
  "loads": [
    {"port_id": "rail_A", "points": [
      {"time_s": 0, "current_a": 0},
      {"time_s": 0.000001, "current_a": 1},
      {"time_s": 0.00001, "current_a": 1}
    ]},
    {"port_id": "rail_B", "points": [
      {"time_s": 0, "current_a": 0},
      {"time_s": 0.000002, "current_a": 2},
      {"time_s": 0.00001, "current_a": 2}
    ]}
  ],
  "output_times_s": [0, 0.000001, 0.000002, 0.00001],
  "max_step_s": 0.0000001
}
```

Ports and topology must already exist in the surrounding
`spike/pdn-network-request/v1` request. Positive current is a sink at the
positive terminal. Values use amperes and seconds; returned deviations use
volts and energies use joules. Signed waveforms are permitted. Each load starts
at `(0,0)`, uses strictly increasing times and shares exactly the same final
time. No waveform is extrapolated or implicitly extended to another horizon.
Load ports must be unique and known; request forms cannot be combined.

Results retain ordered `load_port_ids` and a `load_current_a_by_port` map at
every output point. They contain neither legacy scalar `load_current_a` nor
scalar `load_port_id`; single-load requests retain those legacy fields.
Physical load identities survive request ordering. Input dictionaries remain
unchanged.

## Numerical method and acceptance

For the supplied linear passive descriptor, form columns B for the ordered
load ports and solve E x'=−A x−B u(t). Events are the union of all load corners
and requested output times. Trapezoidal forcing uses B times the vector
midpoint input. Source work is the signed sum `−dt × u_midᵀ Bᵀ x_mid`,
including shared-return cross terms. Stored energy is `xᵀ E x / 2`;
dissipation is `dt × x_midᵀ sym(A) x_mid`. Energies of separate runs cannot
generally be added, because stored energy is quadratic.

The [inductive-cutset correction](PI_SI_PARITY_EXECUTION.md#pi04-s01-transient-consistency)
is linear in load slope, so its responses are combined across loads.
Initial/interior corners use the right derivative; the final endpoint uses the
left derivative. No damping, passivity repair or inferred impedance is added.
The derivation, synthetic fixtures and oracles are original SPIKE work.

Acceptance requires exact asynchronous shared-return RL voltage and energy
references, equal-grid voltage superposition, input-order invariance and
preserved legacy behavior. Identity/horizon/initial-condition failures,
resource admission, cancellation and actual schema/worker round trips must
also pass. Source-bound receipts bind current numerical code and zero-skip
execution. PI04-S01 evidence is rerun after this shared engine change.

Limits remain 16 load ports, 1024 points per load, 2048 output times,
20000 total steps, 8 MiB requests, 16 MiB results and existing dense-work and
conditioning gates. Multiple loads do not relax those budgets. Step refinement
remains necessary for a study's dynamic error; energy consistency alone cannot
establish waveform accuracy.

Scope remains supplied frequency-invariant linear passive lumped networks.
General board extraction, nonlinear regulators, distributed HVDC and measured
signoff remain open. Knowledgeable numerical review is required before release
under `CONTRIBUTING.md`.

## Verification status

PI04-S02 is **Done** for its bounded acceptance: eight zero-skip stage tests
passed in the [source-bound execution](validation/parity/PI04-S02.json).
Combined PI/SI, worker and evidence regressions passed 69 tests with zero skips
in 16.909 s (`build/parity-pi04s02-focused.log`). Nine documentation checks and
the 61-family backlog check also passed.
PI04-S01's eight tests and SI08-S01's seven tests were rerun and their retained
receipts refreshed; pre-change receipts and execution logs remain historical
evidence. The desktop panel test ran actual single/multi-load Python engines
and rejected malformed result identities and currents. TypeScript compilation
and architecture checks passed. No new layout or native visual qualification
is claimed. The full release suite was not rerun; PI04 as a whole remains open.
