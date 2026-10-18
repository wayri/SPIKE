# Supplied decap operating corners

PI03-S01 evaluates an explicit capacitor population across supplied operating
corners using the existing passive PDN MNA solver. This is a bounded step toward
physical decap selection. Location extraction, component catalog ingestion,
automatic optimization and measured qualification remain open.

## Run a study

Call `run_pdn_decap_corners(request)` from
`python.spike_core.pdn_decap_corners`, or invoke the worker method of the same
name with `params: {request: ...}`. The desktop script workspace can use this
Python API. No dedicated desktop editor is introduced by this stage.

The `spike/pdn-decap-corners-request/v1` contract contains:

- `base_request`: an explicit `spike/pdn-network-request/v1` network with
  `load_transient: null`. Existing source and interconnect impedances are kept.
- `corners`: unique IDs with supplied `bias_voltage_v` and `temperature_k`.
- `capacitors`: unique IDs, positive/negative network nodes, source provenance
  and exactly one supplied `capacitance_f`, `esr_ohm`, `esl_h` record per corner.
- `target_impedance_ohm_by_port`: a positive target for every network port.

Bias and temperature are operating-condition metadata. The caller supplies
effective small-signal capacitance and losses appropriate to each corner;
the service does not derive them from nominal ratings or interpolate data.
Tolerance and aging may be represented by additional explicitly supplied
corners. Kelvin, volts, farads, ohms, henries and hertz are used throughout.

All capacitors are installed together at the declared nodes at each corner.
Each becomes an existing `decap` element with its original provenance. The
original request is preserved, and generated requests and identity mappings
remain inspectable. Existing decaps in the base are fixed elements; do not
duplicate a physical component in both the base and the corner population.

## Numerical contract

For angular frequency w, each branch has
`Zc = ESR + j*w*ESL + 1/(j*w*C)`. The existing core stamps that series branch
into the full network, including shared return paths and coupling already
supplied in the base. Target comparisons use each port's driving-point
`abs(Zpp)` at exactly the supplied samples. The worst ratio identifies the
actual corner, port and frequency. A target failure is retained as a valid
study with `meets_target: false`; numerical failure returns no successful
partial corner sweep. A passing sampled target does not bound unsampled
resonances, transfer impedance or transient droop.

Independent original fixtures check scalar parallel-source RLC identities and
a multiport shared-return network. Tests cover exact identity/coverage,
unchanged input, zero parasitics, failed targets, cancellation, malformed
values and aggregate resources. Implementation, derivation and synthetic
fixtures are original SPIKE work; no external implementation or data is used.
The existing equilibrated solve condition limit of 1e12 and backward-error
limit of 1e-10 remain in force, without pseudoinverse or passivity repair.

At most 16 corners and 16 corner-dependent capacitors are admitted, with the
core network limits and additional aggregate work and JSON byte bounds.
Malformed coverage or exceeded bounds require reducing/splitting the explicit
study. Cancellation discards results. Results remain experimental with
`production_qualified: false`. Knowledgeable numerical review is required
before release. This stage does not close PI03 or the full PI/SI parity gate.

See the [request schema](../schemas/pdn-decap-corners-request-v1.schema.json),
[result schema](../schemas/pdn-decap-corners-result-v1.schema.json), and
[retained stage evidence](validation/parity/PI03-S01.json).

## Reproduce the original example

```powershell
.venv/Scripts/python.exe examples/pdn_decap_corners/run_corners.py
```

The [synthetic example](../examples/pdn_decap_corners/run_corners.py) supplies
two explicit operating corners and 161 frequency samples from 1 kHz to 10 MHz.
It saves the actual request and numerical result under
`build/pdn-decap-corners-example/`. These illustrative values are original
synthetic data, without manufacturer or hardware validation claims.

## Development acceptance

On 2026-10-18 the ten stage tests passed with zero skips, and all seven prior
PI/SI stage suites were rerun with refreshed source-bound receipts. Combined
regressions passed 142 tests with zero skips (23.143 s). Architecture,
eight changed documentation files and the 61-family backlog checks passed.
The full release suite was not rerun for this bounded stage; release review
and broader PI/SI qualification remain open.
