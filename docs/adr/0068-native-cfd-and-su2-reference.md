# ADR 0068: Native CFD and SU2 reference execution

## Decision

Use a separately installed SU2 process as an independent CFD reference. Develop
SPIKE-owned numerical kernels in C++, with Python handling admission, runtime
discovery, bounded process execution and evidence. TypeScript displays returned
fields. Rust only supervises the existing heavy worker boundary.

The initial shared case is a two-dimensional laminar lid-driven square cavity.
It establishes momentum, continuity and mesh-refinement evidence before extending
to heat transport and assembly conjugate heat transfer. Availability of a runtime
or agreement on one case does not qualify arbitrary CAD, turbulence, buoyancy,
radiation or coupled thermal results.

## Boundaries

Worker calls accept physical/numerical requests, never executable paths or shell
commands. Runtime overrides are trusted local host configuration. Long runs use
isolated heavy workers, keeping the GUI responsive. Results preserve convergence
status; a stopped or unconverged run is not accepted as a validated solution.

External engine licensing remains separate from the Apache-licensed SPIKE
adapter. SU2 is not copied into SPIKE source. Original mesh generation, numerical
code and test oracles follow the clean-room policy in CONTRIBUTING.md.

## Acceptance

Record executable identity and input hashes, finite fields, continuity residual,
steady convergence and common centerline comparisons on refined meshes. Retain
failed cases and diagnostics. Reference agreement is evidence for this case only.
