# Prescribed-wave rational network transients

SI07-S01 executes a fitted real rational network with simultaneous explicit
incident waves. It returns outgoing waves and port voltage/current histories.
This is experimental zero-state execution of the fitted model, without
arbitrary source/load feedback or measured transient qualification.

## Workflow

Call `run_rational_network_transient(request)` from
`python.spike_core.sparameter_transient`, or invoke the worker method of that
name with `params: {request: ...}`. The desktop script workspace can use the
API; this stage adds no dedicated desktop waveform editor.

The `spike/rational-network-transient-request/v1` contract supplies:

- `fit_request`: the complete [supplied stable-pole fit](SPARAMETER_RATIONAL_FIT.md)
  request. The actual fitter executes internally; the result retains its
  source identity, model coefficients and error/conditioning evidence.
- `incident_waves`: exactly one waveform for every named source port. Each
  has `port_name` and `points` with `time_s` and signed `value_sqrt_w`.
- `output_times_s`: explicit strictly increasing nonnegative observation times
  inside the common waveform horizon.

Every waveform starts at exactly time zero, has at least two strictly
increasing points and ends at exactly the same positive final time. A nonzero
initial incident value is an input step at zero. Model memory starts at zero;
the direct term supplies its instantaneous outgoing response. Interior segments
are continuous linear ramps, including constant holds. No waveform extension,
initial stored state or implicit port excitation is inferred. Original inputs
are preserved and result maps follow source port order.

## Exact PWL integration

For each supplied rate p, the fitted model has `x_prime=-p*x+p*a`. On one
interval of length h with endpoint input values a0 and a1, write z=p*h,
q=exp(-z), w=1-q and phi=1-w/z. The analytic update is

```text
x1 = q*x0 + w*a0 + phi*(a1-a0)
b = D*a + sum_k Rk*xk
```

Stable endpoint weights avoid subtracting large opposing input values.
Small-z series and large-z limits avoid cancellation or overflow in the
coefficient calculation. Intervals whose numerical time representation
collapses are rejected. The event union includes all waveform corners and
observation times, so a port's slope change is never crossed unnoticed.
No numerical time-step refinement is needed for the declared PWL inputs;
adding observation times changes only floating-point roundoff in this model.

Waves are real instantaneous power-normalized values in square-root watts.
For the common real reference R, voltage and current into the modeled network
are `V=sqrt(R)*(a+b)` and `I=(a-b)/sqrt(R)`. These are not an inferred RMS
conversion. Every incident wave is prescribed externally; a port with a=0
has a matched incoming boundary. Arbitrary source/load impedances and their
closed-loop reflections need a separate connection solver. Do not interpret
these prescribed inputs as an arbitrary loaded voltage drive.

## Independent acceptance and limits

Original RC ramp/hold cases are checked against independent augmented matrix
exponentials or convolution references. Multi-input cases verify simultaneous
response, direct feedthrough, state memory and voltage/current conventions.
Small/large time constants, output-grid invariance, exact port/horizon
coverage, precision/resource failures and cancellation are exercised through
Python and actual worker/schema checks. Derivation, code and synthetic
fixtures are original SPIKE work, without external model or measurement data.

Each waveform has at most 1024 points; at most 4096 observations and 20000
event intervals are admitted. Source model limits remain eight ports and
sixteen poles, with aggregate fitting/propagation work bounded before solving.
Requests/results are bounded to 8/16 MiB with final finite-JSON checks.
Numerical failure, rejected fit or cancellation returns no successful partial
waveform. Reduce the study or correct its inputs before retrying.

The response is exact for the supplied PWL inputs to the fitted realization,
up to floating-point arithmetic. The model's agreement with source data is
qualified only at its fit samples. Sharp corners can excite frequencies
outside that range; this stage does not establish their physical accuracy.
It does not establish source causality, nonlinear device behavior, measured
correlation, general termination coupling or complete SI07 parity.
Knowledgeable human numerical review remains required before release.
See the [request schema](../schemas/rational-network-transient-request-v1.schema.json),
[result schema](../schemas/rational-network-transient-result-v1.schema.json), and
[source-bound stage evidence](validation/parity/SI07-S01.json).

## Development acceptance

On 2026-10-18 all eleven source-bound stage tests passed with zero skips.
The original ramp/hold augmented-matrix-exponential reference agreed within
2.22e-16 sqrt(W) for outgoing waves and 5.55e-17 sqrt(W) for final state.
These are fixture-specific errors, without a uniform floating-point error
bound. Simultaneous inputs, V*I=a^2-b^2, output-grid invariance and Decimal
small/large rate-time references passed. All twelve earlier PI/SI suites were
rerun with refreshed receipts. Combined regressions passed 198 tests with
zero skips (13.044 s). Architecture, eight changed documentation files and
the 61-family backlog checks passed. The full release suite was not rerun;
broader qualification and human numerical review remain open.
