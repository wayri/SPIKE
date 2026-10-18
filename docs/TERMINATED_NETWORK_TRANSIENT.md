# Resistively terminated rational network transients

SI07-S02 connects fitted S-parameter models to explicit finite-resistance
Thevenin sources and loads. Reflected waves feed back into the state equations,
and the result retains the fit, terminations, port waves and voltage/current
history. This experimental stage extends
[prescribed-wave execution](RATIONAL_NETWORK_TRANSIENT.md); physical broadband
and measured qualification remain open.

## Workflow and boundary convention

Call `run_terminated_network_transient(request)` from
`python.spike_core.sparameter_terminated`, or invoke the worker method of that
name with `params: {request: ...}`. The desktop script workspace can use the
API; no dedicated desktop termination editor is introduced.

The `spike/terminated-network-transient-request/v1` contract supplies
`fit_request`, `terminations` and `output_times_s`. The actual supplied-pole
fitter executes internally, and its complete result remains attached.
Every source port requires one termination record with `port_name`,
`resistance_ohm` and `voltage_points` containing `time_s`/`voltage_v`.
Record order is arbitrary; result maps use source port order.

Resistances are finite and nonnegative. A zero source voltage defines a
resistive load; zero resistance defines an ideal voltage source only when its
algebraic connection is uniquely supported. All PWL sources start at time zero
and end at the same positive horizon. The initial model state is zero;
nonzero initial source voltage produces the admitted instantaneous response.
Observation times must be explicit, strictly increasing and within that
horizon. No source extension or missing-port termination is inferred.

With reference Z0 and current I positive into the modeled network,

```text
V = sqrt(Z0)*(a+b)
I = (a-b)/sqrt(Z0)
V = Vs - Rt*I
a = Gamma*b + c*Vs
Gamma = (Rt-Z0)/(Rt+Z0), c = sqrt(Z0)/(Rt+Z0)
```

Waves are real instantaneous power-normalized values in sqrt(W); sources use
volts and resistances use ohms. No RMS conversion is inferred. Finite positive
loads now reflect according to their resistance rather than forcing a zero
incident wave. Open/infinite, reactive, nonlinear and time-varying impedances
remain unsupported in this stage.

## Closed state model and numerical admission

Let x stack the fitted pole states, C concatenate the residue matrices,
P stack `pk*I`, and A0 contain diagonal blocks `-pk*I`. With
`b=D*a+C*x`, solve the algebraic connection using

```text
M = I - Gamma*D
Q = solve(M, Gamma*C)
H = solve(M, I)
e = c*Vs
a = Q*x + H*e
x_prime = (A0+P*Q)*x + P*H*e
```

Scaled resistance ratios avoid overflowing `Rt+Z0`. No explicit inverse,
pseudoinverse or artificial series resistor repairs a failed connection.
The loop matrix must satisfy condition at most 1e10, smallest singular value
at least `1e-10*max(1,sigma_max)` and backward-error limit 1e-10.
This also rejects a scalar loop whose
entries nearly cancel even though its formal condition number is one.

The connected state model must have strictly negative pole real parts and
a relative stability margin above 1e-10 against both the resulting matrix
and its construction terms. An unstable, marginal or numerically
unresolved connection returns an error. Stable supplied poles alone do not
guarantee a stable feedback connection, especially for active fitted data.
These checks are numerical admission, without a physical uncertainty budget.

PWL propagation uses an augmented matrix exponential on the union of source
corners and observation times. It solves the connected linear model without
an integration step-size approximation. Per-duration transitions are cached;
finite values, normalized augmented-generator norm bound 1e6 and the port
boundary residual are checked.
There is no general nonlinear iteration or automatic stabilizing repair.

## Evidence, limits and recovery

Original physical capacitor charging/ramp cases check the independently
derived circuit equation `V_prime=(Vs-V)/(Rs*C)`. Ideal-through two-port
fixtures check resistive divider and simultaneous-source nodal equations.
Matched-source equivalence, output-grid invariance, loop/stability failures,
units, precision, resources and cancellation are checked through Python and
the actual worker/schemas. Derivation, implementation and synthetic fixtures
are original SPIKE work, without external code or measured data.

The connected model is bounded to 32 dynamic states and augmented dimension
48, with at most 1024 intervals/observations and 128 distinct interval
durations. Each source has at most 1024 PWL points. Aggregate fitting,
exponential and propagation work is admitted before execution; request/result
limits are 8/16 MiB with a final finite-JSON check. Reduce or split a rejected
study, provide a nonsingular stable connection, or correct source data before
retrying. Failure or cancellation returns no successful partial waveform.

Returned voltages/currents describe this fitted model and declared boundaries.
Sharp PWL corners may excite frequencies outside the fit samples; no physical
accuracy is established there. Arbitrary dynamic terminations, nonlinear
devices, spatial cross-probing and measured waveform correlation remain open.
Knowledgeable human numerical review is required before release.
See the [request schema](../schemas/terminated-network-transient-request-v1.schema.json),
[result schema](../schemas/terminated-network-transient-result-v1.schema.json), and
[source-bound stage evidence](validation/parity/SI07-S02.json).

## Development acceptance

On 2026-10-18 all eleven source-bound stage tests passed with zero skips.
The independent physical RC ramp/hold/reversal reference agreed within
8.88e-16 V, with maximum normalized boundary residual 1.47e-16. These are
fixture-specific errors, without a uniform accuracy claim. Resistive dividers,
simultaneous sources, matched equivalence, stable active models and rejection
of singular/unstable/precision-limited cases passed. All thirteen earlier
PI/SI suites were rerun with refreshed receipts. Combined regressions passed
210 tests with zero skips (20.319 s). Architecture, eight changed documentation
files and the 61-family backlog checks passed. The full release suite was not
rerun; broader qualification and human numerical review remain open.
