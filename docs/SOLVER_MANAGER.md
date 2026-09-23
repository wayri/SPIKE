# Solver Manager

The SPIKE solver manager chooses among implemented native solvers and optional
local process adapters without changing model validity or silently substituting
physics. Its worker contract is `spike/solver-manager/v1`.

## Selection Policy

Recommendations are evaluated in this order:

1. The engine must implement every required workload capability.
2. The runtime state must be `available`, `experimental`,
   `reference_validated`, or `validated`.
3. Catalog order and declared native priority resolve remaining choices.
4. `Approximate`, `experimental`, and `unsupported` status remains visible.

Current workloads include DC PI, quasi-static AC PI, geometry-derived
transient PI, explicit-netlist circuit co-simulation, full-wave comparison,
thermal airflow, and EMI far-field analysis. A missing recommendation is a
capability gap, not an instruction to use a weaker model.

Use:

```text
spike solver-manager
spike solver-recommend dc_pi
spike solver-recommend emi_radiation
```

## Local Registration

`solver-register` stores an explicit absolute local path in SPIKE's private
per-user state. It does not download, install, load, compile, probe, or execute
the target. `solver-unregister` removes only that registration and never deletes
third-party files.

```text
spike solver-register external.sparselizard C:\tools\sparselizard
spike solver-register external.elmer C:\tools\Elmer
spike solver-unregister external.sparselizard
```

Managed installation remains disabled until each package has a signed manifest,
pinned digest, SBOM, complete license notices/source obligations, platform and
ABI metadata, atomic activation, and rollback. Raw `PATH` discovery is not an
authentication decision.

## Tuning

Tuning is an allowlisted, typed, range-checked profile. Arbitrary command-line
arguments, environment variables, source code, formulations, library paths, and
PETSc option strings are not accepted.

```text
spike solver-tune native.sparse linear_backend=\"superlu\" thread_count=4
spike solver-tune external.openems mesh_resolution_mm=0.25 max_solver_time_s=7200
```

Profiles currently cover native sparse assembly/solve policy, openEMS resource
and mesh controls, candidate sparseLizard FEM controls, and OpenFOAM iteration
policy. Saving a sparseLizard or OpenFOAM profile does not make its adapter
runnable. Elmer currently has no tuning profile because SPIKE has no Elmer
adapter whose inputs could be safely or meaningfully tuned.

## Elmer Boundary

Elmer discovery accepts only an explicit registration, `SPIKE_ELMER_HOME`, a
normal `PATH` lookup, or the optional local runtime location. Discovering
`ElmerSolver` records installation evidence only: SPIKE does not execute it,
generate `.sif` cases, import results, or expose PI, SI, thermal, or EMI
capabilities. The catalog uses `installed_adapter_pending` with an empty
implemented capability list until a separately reviewed process adapter and
validation corpus exist.

## sparseLizard Boundary

sparseLizard is a GPL-2.0-or-later C++ FEM library, not a documented stable
general-purpose JSON command-line solver. SPIKE therefore does not execute an
arbitrary `sparselizard` or `slexe` found on `PATH`, load its library into the
desktop process, use `spylizard`, or compile project-supplied C++.

The intended adapter is a separately built, process-isolated
`spike-sparselizard-adapter` with a fixed JSON/file protocol. Before execution
can be enabled it must provide:

- a signed manifest and pinned executable digest;
- adapter, sparseLizard, compiler ABI, PETSc/MUMPS/SLEPc, Gmsh, MPI, and scalar
  configuration provenance;
- bounded mesh, memory, runtime, process-tree, log, and artifact policies;
- normalized geometry/material/port input and result contracts;
- DC conduction and mesh-convergence fixtures before AC/electrothermal work;
- independent analytical, external-solver, and measured-board correlation.

Candidate upstream functions such as DC conduction, electrothermal coupling,
capacitance, harmonic magnetodynamics, Maxwell fields, and lumped-circuit
coupling are displayed separately from implemented SPIKE adapter capabilities.
Their presence never enables a Run command.

Because a linked adapter is a GPL derivative, redistribution requires a
GPL-compatible adapter license and the applicable source, notice, and dependency
obligations. The process boundary is an engineering isolation measure, not legal
advice or an automatic commercial-licensing exemption.

## EMI Pipeline

The manager publishes distinct execution and validation stages:

| Stage | Current status |
|---|---|
| PI/SI pre-pass | Available with native approximate models |
| Net screening | Available as a deterministic ranking heuristic |
| Closed-loop SPICE | Unavailable until geometry/device coupling is validated |
| Full-wave openEMS execution | Runnable when the discovered engine is `experimental` or `reference_validated` and preflight accepts the geometry, stackup, and explicit ports |
| NF2FF result/dashboard | Implemented for an explicit `spike/openems-far-field-request/v1`; imported field components, directivity, radiated power, polar cuts, and validity boundaries are shown |
| Arbitrary-PCB validation | Not established by the reference fixture; board-specific convergence and independent correlation are required |
| EMI compliance | Unavailable; no dashboard value is a regulatory verdict |

`recommend_emi_nets` ranks explicitly supplied pre-pass metrics such as
`dV/dt`, `dI/dt`, peak current, loop area, and return discontinuities. The result
contract is `spike/emi-prepass-screening/v1` and is labeled `screening_only`.
It prioritizes engineering review; it does not calculate radiation, predict an
EMI test result, or establish compliance.

The desktop EMI workbench includes an explicit lumped-port editor. Each port
has 3D start/stop coordinates, direction, impedance, and excitation state, and
exactly one port must be excited for a run. The UI can preflight and prepare an
authenticated case, run the isolated openEMS adapter, import a shape-checked
NF2FF result, and retain the result in the far-field dashboard and report.

`reference_validated` is deliberately runnable. It means only that the exact
openEMS/adapter version pair passed the named simple-patch fixture and its mesh-
convergence thresholds. It does not transfer that validation to an arbitrary
PCB, enclosure, cable, material set, or EMC standard. Each PCB field result
therefore retains its own `not_validated` status until project-specific evidence
is attached.

## Environment Inputs

Versioned environment profiles can be listed, materialized, and checked for PI,
SI, thermal, or EMI input readiness through the worker protocol and CLI. The
sealed/potted, automotive, marine, aerospace-altitude, and vacuum/space presets
are metadata and capability gates. They provide explicit operating assumptions
and required inputs; they do not install a solver, validate its physics, qualify
a product, or establish certification.

## Persistence And Security

Solver state is strict JSON with a 1 MiB pre-parse limit, finite numeric values,
atomic same-directory replacement, and private file permissions where the
platform supports them. The state directory is selected by `SPIKE_STATE_HOME`
for controlled deployments/tests, `%LOCALAPPDATA%\SPIKE\state` on Windows,
`~/Library/Application Support/SPIKE/state` on macOS, or XDG state conventions
on Linux.
