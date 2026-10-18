# Supplied stable-pole rational network fit

SI08-S04 fits a real proper rational S-parameter model using explicitly
supplied stable real poles. It is a bounded experimental step toward reusable
broadband SI/PI macromodels. It does not perform automatic pole selection or
certify the physical accuracy or causality of the source data.

## Workflow

Call `fit_sparameter_rational(request)` from
`python.spike_core.sparameter_rational`, or invoke the worker method of that
name with `params: {request: ...}`. The desktop script workspace can invoke
the API. This stage does not insert the model automatically into a transient
solver or introduce a dedicated desktop editor.

The `spike/sparameter-rational-fit-request/v1` contract supplies:

- `source`: an explicit sampled S network with ID, unique ordered port names,
  one positive real scalar reference impedance, strictly increasing
  nonnegative frequencies in hertz and receiver/source complex-pair matrices.
- `pole_rates_rad_s`: distinct positive rates p, in radians per second, in
  caller order. Model poles are s=-p. These rates are not frequencies in hertz.
- `max_absolute_error`: a positive dimensionless limit on the largest complex
  entry error over every supplied frequency and port pair.

Any source DC sample must be exactly real. No DC, interpolation, pole
relocation, weighting, delay, port transformation or passivity repair is
inferred. Source snapshots/digests remain separate from the reconstructed
network and model coefficients.

## Model and original derivation

For complex frequency s, the fitted model is

```text
S(s) = D + sum_k Rk * pk/(s+pk)
xk_prime = -pk*xk + pk*a
b = D*a + sum_k Rk*xk
```

Each xk is a vector of incident-wave states, and D and Rk are real matrices
in the original receiver/source order. Rates have inverse-time units;
coefficients and S are dimensionless. Positive rates make the supplied poles
strictly stable. This proper rational realization is causal by construction,
including instantaneous direct feedthrough D. It does not prove that the
sampled source is causal or that an underconstrained fit is physically valid.

At s=j*2*pi*f, form columns 1 and pk/(pk+j*2*pi*f). Stack their real and
imaginary parts and the corresponding source entries into a real least-squares
system. Unit-2-norm column scaling controls arbitrary column magnitude.
One full-rank solve fits all ordered matrix entries simultaneously. The
equilibrated condition must be at most 1e10, and a normwise least-squares
optimality residual must be at most 1e-10. Rank-deficient or ill-conditioned
fits fail without a truncated-rank rescue or artificial regularization.

The result reports actual maximum and RMS complex entry errors; the maximum
must satisfy the requested limit before success. It also reports sampled
largest singular value and the conservative bound
`norm(D,Frobenius)+sum(norm(Rk,Frobenius))`. Since each scalar basis has
magnitude at most one on the imaginary axis, this bounds the model's spectral
norm there, up to floating-point evaluation. A bound above one is inconclusive
and does not reject an intentionally active network. This is not passivity
enforcement, and sampled passivity alone does not establish broadband passivity.

Independent original analytic first-order and multiport fixtures verify known
real coefficients, source reconstruction, supplied pole order and active/
nonreciprocal data. The step realization has response
`D + sum(Rk*(1-exp(-pk*t)))` for unit incident steps; independent time/frequency
references check the construction. Failure, precision, resource and
cancellation cases are checked through Python and the actual worker/schemas.
Derivation, implementation and synthetic fixtures are original SPIKE work,
using no external implementation, catalog model or measurement data.

## Limits and recovery

At most eight ports, sixteen rates and 2..2048 source samples are supported,
with bounded matrix entries and cumulative least-squares work. Request/result
limits are 8/16 MiB with final finite-JSON admission. A failed error limit,
conditioning, numerical failure or cancellation returns no successful partial
model. Supply applicable rates, improve source coverage or reduce the study
before retrying. Loosening the error limit changes the acceptance requested
by the caller and does not improve model accuracy.

Frequency grids that lose their strict ordering when represented as numerical
solver inputs are rejected. Distinct source frequencies are not silently
collapsed into repeated observations.

No claim is made for accuracy between or outside supplied samples, distributed
delay, complex conjugate poles, nonlinear behavior or measured qualification.
Automatic vector fitting, general passive causal fitting and release review
remain open. Knowledgeable human numerical review is required before release.
See the [request schema](../schemas/sparameter-rational-fit-request-v1.schema.json),
[result schema](../schemas/sparameter-rational-fit-result-v1.schema.json), and
[source-bound stage evidence](validation/parity/SI08-S04.json).

## Development acceptance

On 2026-10-18 all eleven source-bound stage tests passed with zero skips.
The RC/Debye witness had maximum complex entry error 1.11e-16, RMS error
5.39e-17, equilibrated condition 4.52 and optimality residual 9.30e-17.
Independent step and numerical impulse-transform references passed. These
are fixture-specific results, without a uniform accuracy claim. All eleven
earlier PI/SI suites were rerun with refreshed receipts. Combined regressions
passed 186 tests with zero skips (15.343 s). Architecture, eight changed
documentation files and the 61-family backlog checks passed. The full release
suite was not rerun; broader qualification and human review remain open.
