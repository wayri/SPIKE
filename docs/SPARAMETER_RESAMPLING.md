# Explicit S-parameter resampling and DC policy

SI08-S03 creates a separate sampled network on an explicit target frequency
grid. It retains the source and the complete interpolation mapping. It is a
bounded experimental preparation step for SI/PI network workflows, without
causality, broadband fitting or time-domain qualification.

## Workflow

Call `resample_sparameter_network(request)` from
`python.spike_core.sparameter_sampling`, or invoke the worker method of that
name with `params: {request: ...}`. The API is available from the desktop
script workspace; existing channel and network composition services keep their
own grid admission rules. No implicit resampling is added to them.

The `spike/sparameter-resampling-request/v1` contract contains `source`,
`target_frequencies_hz` and `dc_policy`. Source fields are `id`, unique ordered
`port_names`, one positive real scalar `reference_impedance_ohm`,
`frequencies_hz` and `s_parameters`. Matrices use receiver/source ordering
and complex `{real, imag}` entries. Frequencies are hertz, nonnegative and
strictly increasing. Source and target grids may be nonuniform.

| DC policy | Supported behavior |
| --- | --- |
| `{mode: "require_source"}` | Use only the supplied source range. A DC sample is needed only when the requested range requires it. |
| `{mode: "supplied", s_parameters: matrix}` | Explicitly prepend a supplied DC matrix when the source begins above zero. Interpolation between DC and the first positive sample is then allowed. |

An existing source DC point cannot be overridden. At a real-system DC point,
every matrix entry must have exactly zero imaginary part. This is an explicit
admission rule; values are not silently clipped. No high-frequency extension,
constant endpoint continuation, inferred DC, port reordering or reference
renormalization occurs. Unsupported target frequencies return a structured
error and no successful partial sweep.

## Method, evidence and interpretation

At a target f between adjacent support samples fl and fu, let
`w=(f-fl)/(fu-fl)`. Entrywise complex Cartesian interpolation is
`S(f)=(1-w)*S(fl)+w*S(fu)`. Exact source samples are copied directly,
including their original complex-pair records. The result records each
sample's kind, support frequencies and upper weight, plus its largest singular
value. The supplied DC matrix and source snapshot have separate provenance
from the derived grid. Original requests remain unchanged.

For any two passive support matrices, the operator norm triangle inequality
gives `norm(S(f)) <= (1-w)*norm(S(fl))+w*norm(S(fu)) <= 1`.
Thus interpolation preserves sampled passivity between passive support
matrices at the common real reference. Active inputs are also accepted and
retained; SVD is a diagnostic, without passivity repair. The statement does
not establish continuous physical accuracy or causality. Linear interpolation
of a pure delay can add artificial attenuation, especially on a coarse grid.

Independent original tests establish exact affine-complex interpolation,
multiport identity, supplied DC behavior, active/nonreciprocal preservation
and passive convexity. An analytic delayed-line reference demonstrates
second-order grid refinement of interpolation error for the tested sweep.
This checks approximation error, without promising an error bound for an
arbitrary supplied dataset or establishing a causal impulse response.
Code, derivation and synthetic fixtures are original SPIKE work; no external
implementation or measurement data is used.

## Limits and recovery

There are at most 16 ports, 4096 source samples and 4096 target samples.
Combined source/target matrix entries are bounded to 262144, and target SVD
work is limited before evaluation. Request/result limits are 8/16 MiB with a
final finite-JSON check. Cancellation returns no successful partial dataset.
Reduce or split an oversized study, supply applicable DC data explicitly, or
correct the source range and matrix dimensions before retrying. Intervals or
interior weights that collapse at floating-point precision are rejected;
the service does not silently replace an interior target with an endpoint.

The result is experimental with `production_qualified: false`. SI08 remains
open for causality, calibrated uncertainty and passive causal fitting.
Knowledgeable human numerical review remains required before release.
See the [request schema](../schemas/sparameter-resampling-request-v1.schema.json),
[result schema](../schemas/sparameter-resampling-result-v1.schema.json), and
[source-bound stage evidence](validation/parity/SI08-S03.json).

## Development acceptance

On 2026-10-18 all nine source-bound stage tests passed with zero skips. For a
3 ns delayed line over 100 MHz, midpoint maximum errors at 4/8/16/32 source
intervals were 0.02763008, 0.00693154, 0.00173439 and 0.00043369, matching
`1-cos(pi*df*tau)`. Ratios approached four at each refinement. These are
fixture-specific interpolation errors, without a uniform broadband claim.
All ten earlier PI/SI suites were rerun with refreshed receipts. Combined
regressions passed 174 tests with zero skips (19.242 s). Architecture, eight
changed documentation files and the 61-family backlog checks passed. The full
release suite was not rerun; broader qualification and human numerical review
remain open.
