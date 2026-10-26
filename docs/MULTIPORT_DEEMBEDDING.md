<!-- SPDX-License-Identifier: Apache-2.0 -->
# Supplied coupled multiport fixture removal

This experimental supplied-network increment addresses the multiport algebra gap in
SI08. It removes one explicitly supplied coupled 2N-port fixture around an
N-port DUT, including odd port counts and fully reflecting DUTs. It does not
identify or calibrate the fixture from measurements. SI08 remains in progress.

## Workflow and contract

Call `deembed_multiport(request)` from
`python.spike_core.solvers.signal_integrity.networks.sparameter_multiport_deembedding`, or use:

```text
.venv-emerge3/Scripts/python.exe -B examples/multiport_deembedding/run_fixture.py --output build/multiport-demo.json
.venv-emerge3/Scripts/python.exe -B examples/multiport_deembedding/run_fixture.py --request REQUEST.json --output NEW_RESULT.json
```

Outputs must be new files. The default example is an original three-port
synthetic DUT behind three matched 0.8-amplitude paths; its measured S is
0.64 times the DUT S. No measurement or external fixture data is bundled.

The strict local `spike/multiport-deembedding-request/v1` record contains only
`contract`, `measured`, `fixture`, `external_ports`, and `dut_ports`. Each network
contains only `id`, unique `port_names`, positive real scalar
`reference_impedance_ohm`, `frequencies_hz` and `s_parameters`. Matrices use
`S[receiver][source]`, each value `{real, imag}`. Both sources need distinct IDs,
the exact same nonnegative strictly increasing frequency grid and reference.
At DC all supplied imaginary parts must be exactly zero. DC here is supplied
real algebraic circuit data, not a static-waveguide extraction claim.

`external_ports` must equal the measured ordered port list. Together with the
ordered `dut_ports`, they partition every fixture port exactly once. Fixture
storage order is arbitrary; mapping is explicit. Every DUT port is connected;
there are no silently terminated or discarded fixture ports. One to eight DUT
ports and two to sixteen fixture ports are admitted. The request/result bounds
are 8/16 MiB, each network is limited to 131072 complex entries, and the grid
to 4096 samples. Oversized output estimates reject before complex allocation.
Cancellation is checked during admission, before each sample and before return.
No successful partial sweep is returned.

The separate result retains the entire immutable source request and its SHA256
of canonical finite JSON, derived port names, source grid/reference, diagnostics
and explicit limitations. It remains `model_status=experimental` and
`production_qualified=false`. Worker method `deembed_multiport` accepts exactly
`params: {request: REQUEST}`. Strict nested request/result schemas are registered
with unique canonical IDs; dynamic grid/map equality, entry budgets and numerical
checks remain authoritative in the worker.

In the desktop S-parameter workbench choose **Multiport fixture removal**.
Import or paste a complete request, review both independently ordered port sets
and run. The panel retains an immutable source/result capture, exposes selected
raw DUT matrices and worker diagnostics, and exports the capture as JSON.
Editing/importing invalidates prior results. Browser preview disables execution.
Heavy-worker dispatch uses operation-specific cancellation and late-response
rejection. Actual JSONL, schema, headless UI and TypeScript checks are distinct
from native interactive acceptance. Current native observations and SI08-S05
status are retained in the [integration record](validation/SI08_MULTIPORT_INTEGRATION_20261024.md).
Software integration does not complete full SI08 or qualify calibration.

## Independent block-wave derivation

Partition the supplied fixture F into external E and internal I ports, and
denote the DUT scattering matrix D. Power-wave amplitudes have units sqrt(W);
S, F, D and all matrix condition numbers are dimensionless; frequency is Hz
and the reference is ohms. With a common real positive reference, joining ports
exchanges incident and outgoing waves without a polarity or reference change:

```text
bE = FEE aE + FEI aI
bI = FIE aE + FII aI
aD = bI, aI = bD = D aD
M = FEE + FEI D (I - FII D)^(-1) FIE
X = FEI^(-1) (M - FEE) FIE^(-1)
X (I - FII D) = D
(I + X FII) D = X
```

The implementation uses left and transposed right linear solves, never an
explicit inverse or pseudoinverse. Unlike a wave-chain formulation, it requires
invertible fixture transmission blocks, not an invertible DUT S21 block. It
admits dense cross-coupling across all fixture ports. Conjugate transposition
would solve a different physical system and is not used in the right solve.

Each fixture transmission block must have minimum singular value at least
1e-12 and 2-norm condition at most 1e8; their condition product must be at most
1e8. Recovery `I+X FII` and feedback `I-FII D` must each have condition at most
1e8. Every solve must satisfy Frobenius backward residual
`||A Y-B|| / max(||A|| ||Y||+||B||, tiny) <= 1e-10`. Reconnecting the recovered
DUT must reproduce the measured S with
`||M_rebuilt-M||/max(1,||M||) <= 1e-10`.

These are conditioning, representation and backward-error screens, not an
accuracy guarantee for noisy measurements. Small fixture transmission can
amplify input error even with a condition number of one. No clipping,
regularization, fixture inversion repair, inferred DC, extrapolation,
interpolation or hidden reference-plane conversion occurs. Sampled largest
singular values are diagnostics; active/nonreciprocal DUTs are preserved.
Neither source causality nor broadband passivity follows from those values.

## References, verification and remaining gates

Primary source actually reviewed: R. B. Marks and D. F. Williams,
*A General Waveguide Circuit Theory*, Journal of Research of NIST 97(5),
533-562 (1992), accepted 22 May 1992, sections 3.4 and 5:
[NIST original](https://nistdigitalarchives.contentdm.oclc.org/digital/api/collection/p16009coll6/id/74796/download).
Section 3.4 supplies the multiport linear scattering convention; section 5
distinguishes real-reference power waves and their net-power identity. The
block elimination above and simultaneous-wave test oracles are independently
authored SPIKE work. No external code, implementation examples, data or fixtures
were copied, translated or adapted. Existing NumPy linear solves/SVD and sampled
network admission are reused; no dependency was added.

See the [independent oracle record](validation/MULTIPORT_DEEMBEDDING_ORACLES_20261024.md)
and [family closure campaign](SI08_FAMILY_CLOSURE.md) for executed checks and
remaining scope. Synthetic algebra does not establish calibrated fixture
accuracy, measurement covariance/uncertainty, physical source validity,
intersample accuracy, transient stability, general passive fitting or release
qualification. Knowledgeable human numerical review remains required.

## Desktop integration

Use **Solver manager → Coupled multiport fixture de-embedding** to open the exact fixture tool. Import the complete request, use Run/Tutor to resolve required inputs, then review and export the retained source/result capture. The source worker method is `deembed_multiport` with `{request: ...}` parameters. This transport and UI integration does not establish measurement calibration, installed-package, visual or production qualification.
