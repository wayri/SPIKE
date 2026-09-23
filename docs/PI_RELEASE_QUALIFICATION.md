# PI Release Qualification

SPIKE uses a fail-closed release qualification for the Power Integrity suite.
The existence of a command, panel, solver entry, or result contract is not
evidence that a workflow is suitable for engineering signoff.

Run the gate from the repository root:

```powershell
python -m python.spike_core.cli --output build/pi-release-qualification.json `
  pi-release-qualification `
  --runtime-report build/release-runtime-qualification-current.json `
  --benchmark-report build/native-benchmark-current.json
```

The command exits with the validation exit code while any required check is
blocked. Its JSON output uses `spike/pi-release-qualification/v1` and is the
release-facing record consumed by documentation and packaging review.

## Required Workflows

The first deployable PI release requires all of these native workflows:

- DC conductor analysis.
- AC/RLCG extraction.
- PDN target analysis and capacitor optimization.
- Geometry-derived transient analysis.
- A native SPICE-compatible MNA circuit engine.
- Iterative field/circuit co-simulation.

Each workflow must be owned by a `spike.native.*` solver, have a release and
validation state of `reference_validated` or `validated`, and cite non-empty
validation evidence. An external engine may provide comparison evidence, but
cannot satisfy the native release requirement.

## Native Linear MNA Boundary

The bounded native linear MNA core is implemented as
`spike/native-mna-request/v1` and `spike/native-mna-result/v1`. Its focused
tests cover DC operating point, AC small-signal analysis, fixed-step
backward-Euler transient analysis, independent voltage/current sources, and
VCCS, VCVS, CCCS, and CCVS dependent sources.

This implementation is **experimental** and is not a PI release-qualified
workflow. The service and CLI can compile and run reviewed SPICE workspaces
through native MNA, and an explicit reviewed package can run the deterministic
native PEEC-reduction/native-MNA fixed-point route. These integrations do not
make the workflow validated and their results are not release-promotion
evidence.

The following remain unsupported and must fail closed rather than be inferred:

- Nonlinear semiconductor devices and behavioral sources.
- Adaptive timestepping, sparse or iterative matrix backends, and large-circuit
  resource qualification.
- General iterative field/circuit coupling, automatic PEEC-network-to-circuit
  compilation, and electrothermal feedback. The implemented reviewed
  fixed-point PEEC-reduction/native-MNA route remains experimental and is not
  sufficient for this gate.

Native MNA and the fixed-point field/circuit route can satisfy their
required-workflow gates only after their existing compiler/service/CLI paths,
request/result provenance, analytical validation fixtures, independent
comparison, and measured-board evidence meet the release policy.

## Other Hard Gates

- The source and packaged worker qualification must pass with identical
  capability snapshot digests.
- The permanent native benchmark evidence embedded in the parity-qualified
  runtime snapshot must have zero failures and zero skips. An explicitly
  supplied report may be used for controlled validation runs.
- Missing reports, unknown states, or unreadable evidence block release.

## Current State

`build/pi-release-qualification-current.json` is currently `blocked`. Runtime
parity and the explicit 15/15 native benchmark evidence pass, while all six required
workflow promotions remain blocked. Each blocked workflow now includes explicit
machine-readable `blocking_reasons` rather than a generic unavailable state.
This is intentional: DC remains approximate, AC and transient remain
experimental, PDN placement is screening-only, ngspice handoff is one-way,
native linear MNA and the reviewed fixed-point field/circuit route remain
experimental, and no validated general FEA or electrothermal co-simulation is
available.

The former fixed 1,200-branch PEEC ceiling has been removed. Dense PEEC and
transient admission are derived from the configured solver RAM budget, with a
2 GB minimum and optional stricter user cap. The Modular board AC audit run in
`build/realboard-modular-ac-resource-admitted-current.json` completed with
1,207 filaments; its 2 GB budget admitted up to 3,813 dense PEEC branches. This
demonstrates capacity admission and real-design execution, not validated
accuracy or engineering-signoff eligibility.

The gate must not be weakened to produce an installer. Solver implementation,
correlation, and validation evidence must change first.
