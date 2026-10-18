# Explicit two-port fixture removal

SI08-S02 removes two supplied cascaded fixture models from sampled S data.
It preserves the original measured and fixture datasets and returns a separate
derived network with source digests and per-sample numerical diagnostics.
The method is experimental; calibration accuracy, uncertainty, causality and
general multiport fixture removal remain open.

## Workflow and orientation

Call `deembed_two_port(request)` in
`python.spike_core.sparameter_deembedding`, or invoke worker method
`deembed_two_port` with `params: {request: ...}`. This API is available from
the desktop script workspace; this stage adds no dedicated desktop editor.
The `spike/two-port-deembedding-request/v1` contract supplies `measured`,
`left_fixture` and `right_fixture`. Each contains a distinct `id`, two ordered
`port_names`, a positive scalar `reference_impedance_ohm`, `frequencies_hz`,
and `s_parameters` with complex `{real, imag}` entries.

All three frequency grids and real reference impedances must match exactly.
Frequencies are nonnegative and strictly increasing; an explicit DC sample
and nonuniform grids are supported. No DC point, interpolation, extrapolation
or renormalization is inferred. Samples use `S[receiver][source]`, with `b=S*a`
for real-reference power waves. Ports must be ordered as follows:

| Dataset | First port | Second port |
| --- | --- | --- |
| Measured cascade | Left exterior | Right exterior |
| Left fixture | Left exterior | DUT left |
| Right fixture | DUT right | Right exterior |

The exterior names must match exactly. The two interior names must be unique;
they become the derived network's ordered ports. A reversed fixture requires
an explicit caller transformation before admission. This stage does not infer
orientation or reference planes from filenames.

## Original derivation and numerical limits

At one frequency the two scattering equations give
`b1=S11*a1+S12*a2` and `b2=S21*a1+S22*a2`. Solving the second for `a1`
defines the dimensionless chain relation `[a1,b1] = T*[b2,a2]`:

```text
T = [[1/S21,       -S22/S21],
     [S11/S21, S12-S11*S22/S21]]
Tmeasured = Tleft * Tdut * Tright
```

Left and right linear solves recover `Tdut` without an explicit inverse.
Then `S21=1/T00`, `S22=-T01/T00`, `S11=T10/T00` and
`S12=T11-T10*T01/T00`. This avoids impedance conversions that cannot
represent an ideal through. It retains nonreciprocal and active DUT data.
Per-sample SVD reports the derived largest singular value without clipping
or passivity repair. Passive samples alone do not establish causality.

Every supplied `abs(S21)` must be at least 1e-12 and derived `abs(T00)`
at least 1e-12. These explicit representation floors reject unstable
conversions; they are not measured dynamic-range claims. Each fixture's
dimensionless chain condition number and their product must be at most 1e8.
Finite reconstructed chain agreement must be within relative residual 1e-10.
No pseudoinverse or regularization rescues singular fixtures. Conditioning and
reconstruction are numerical checks, without an uncertainty budget for supplied
measurements. Errors in fixture data can still dominate a de-embedded result.

Original matched-wave, reflective and directional fixtures independently
verify recovery. A separate internal-wave connection solve forms cascades
without reusing the chain conversion. Tests cover source preservation, active
DUTs, orientation, DC/nonuniform grids, singular/ill-conditioned fixtures,
resource limits and cancellation. Derivation, implementation and synthetic
fixtures are original SPIKE work; no external code or measurement data is used.

## Recovery and scope

The request and result are bounded to 8 and 16 MiB, with at most 4096 samples.
Invalid coverage or a conditioning failure returns a structured error and no
successful partial dataset. Cancellation discards the derived result. Correct
source orientation, use compatible references/grids or reduce an oversized
study before retrying; poor fixture transmission needs a separately qualified
measurement/modeling approach.

This stage establishes supplied-model algebra only. It does not calibrate a
VNA, derive fixtures from a 2x-through, perform TRL/SOLT, remove arbitrary
multiport couplings or qualify SI08 as complete. Knowledgeable human numerical
review remains required before release.

See the [request schema](../schemas/two-port-deembedding-request-v1.schema.json),
[result schema](../schemas/two-port-deembedding-result-v1.schema.json), and
[source-bound stage evidence](validation/parity/SI08-S02.json).

## Development acceptance

On 2026-10-18 all ten source-bound stage tests passed with zero skips,
including actual worker/schema and ideal-through fixture checks. Independent
internal-wave recovery errors were at most 2e-15 for the tested reflective,
directional active DUT; matched-delay cases were within 5e-15. These are
fixture-specific errors, without a uniform accuracy claim over the admitted
conditioning range. All nine earlier PI/SI stage suites were rerun with
refreshed receipts. Combined regressions passed 164 tests with zero skips
(14.224 s). Architecture, eight changed documentation files and the 61-family
backlog checks passed. The full release suite was not rerun for this bounded
stage; broader qualification and human numerical review remain open.
