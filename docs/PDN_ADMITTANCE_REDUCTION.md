# Explicit passive PDN port reduction

PI02-S02 terminates auxiliary ports of a supplied sampled admittance network
and retains selected ports in explicit order. Use `reduce_pdn_admittance` from
`python/spike_core/pdn_admittance_reduction.py` or the worker method with exactly
`{request: ...}`. The request contract is
`spike/pdn-admittance-reduction-request/v1`; the installed offline schema checks
structure, and numerical admission additionally checks identities and samples.

Supply a `source` containing ordered unique `nodes`, `reference_node`, positive
strictly increasing `frequencies_hz`, `admittance_s`, `model_status`, `source_id`
and `context_digest`. Admittance uses siemens and complex `{real, imag}` values
in `[frequency][receiver][source]` order. Status is approximate or experimental;
the reduction never promotes it. `dielectric_admittance_source(result)` copies
the finite-dielectric solver's samples and retains its reference, context and
input digest as source identity. Projection is not independent source validation.

`retained_nodes` and `eliminated_nodes` must partition every source node exactly
once. `termination_admittance_s` contains a full passive matrix at each source
frequency in the explicit eliminated-node order, using the same reference.
Cross-coupled loads are permitted. Zero termination represents floating ports.
No interpolation, reference conversion, missing load or frequency extension is
inferred. A singular floating-port solve fails explicitly.

## Derivation and numerical evidence

Partition `I=YV` into retained p and auxiliary q ports. With passive termination
YL, KCL gives `(Yqq+YL)Vq=−Yqp Vp`. Solve directly and form
`Yred=Ypp−Ypq solve(Yqq+YL,Yqp)`. Auxiliary basis voltages are retained in the
same explicit q/p order. No pseudoinverse or arbitrary regularization is used.

For `T=[I;Vq_basis]` reordered into the original source order, independent power
accounting gives `Yred=T†Y T+Vq_basis† YL Vq_basis`. This follows auxiliary KCL
and holds without reciprocity. Real `V†I` is average dissipation for RMS
phasors; conventional complex power is its conjugate. Passivity is checked using
Hermitian dissipative parts of source, termination and reduced matrices, with
explicit relative roundoff tolerances. Matrices are never repaired or symmetrized.

Independent resistor/circuit and complex passive references test Schur response,
floating and terminated ports, order, auxiliary voltages and power. Actual
finite-dielectric extraction passes through projection and the owned worker to
an independently derived loaded-plate response. Active, malformed, singular,
ill-conditioned or resource-exceeding inputs and cancellation must fail before
any partial success is returned. The derivation, implementation and synthetic
fixtures are original SPIKE work; no external implementation was consulted.

Results retain source/context/reference identities, input/source digests, ordered
maps, supplied termination matrices, dimensionless auxiliary basis voltages,
power identity and conditioning/residual evidence.
Sampling bounds are 32 source nodes and 512 frequencies, with explicit input,
matrix-work and output limits: 262144 combined source/load matrix entries,
100 million estimated cubic work units, 8 MiB requests and 16 MiB results.
The existing equilibrated solve rejects condition
numbers above 1e12 and backward errors above 1e-10.
An independently recomputed scaled equation residual must be at most 1e-10;
power identity error at most 1e-9. The normalized Hermitian minimum eigenvalue
must be at least −1e-10 for each source, load and reduced sample, without repair.

This is exact algebraic elimination within admitted numerical tolerances at the
supplied frequencies. It does not fit a causal broadband state-space model,
establish frequency-interpolation validity, infer geometry or qualify measured
boards. General plane/via/package extraction, material dispersion and causal
model reduction remain open. Knowledgeable human numerical review is required
before release under `CONTRIBUTING.md`.

## Stage verification

PI02-S02 is **Done** for its bounded acceptance. Nine zero-skip checks passed
in the [source-bound execution](validation/parity/PI02-S02.json), including
actual finite-dielectric extraction, projection, owned-worker execution and
request/result schemas. Four affected earlier stages were re-executed and their
retained receipts refreshed; prior receipts and logs remain historical evidence.
Full release validation remains separate, and PI02 as a whole remains open.

Combined numerical, worker, schema and evidence regressions passed 99 tests
with zero skips in 19.194 s (`build/parity-pi02s02-focused.log`). Architecture,
nine documentation checks and the 61-family backlog check passed.
