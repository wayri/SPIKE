# Local solver capability benchmarks

SPDX-License-Identifier: MIT

Copyright (c) 2026 SigHarmonic

```powershell
python benchmarks/capability_suite/run_benchmarks.py --native-build D:/PROJECTS-DEV/SPIKES-build/windows-msvc-release
```

This permanent runner supersedes the release-freeze staging script under `build/`.
Reports, logs and SHA-256 manifests go into unique `build/capability-benchmarks/run-*`
directories. The runner does not mutate solver sources or qualify a release.

It measures five repeats after one warm-up for complex lossless-line transmission,
complex RC response, 3D anisotropic thermal refinement, steady electrothermal
equilibria, the existing extraction/PI corpus, and available native mathematical
executables. The regression suite additionally exercises implicit transient diode
field coupling, exact timestep/matrix solutions, nonlinear convergence, storage,
cancellation and input rejection. Transient regression timing is not a repeated
performance benchmark.

Numerical/operation and adapter/metadata evidence are reported separately; not
every unit case is an independent mathematical oracle. Skips and changed tracked
inputs prevent an executed-check pass. Native executables are prebuilt and hashed,
not rebuilt/source-attested here. Python source and thermal JSON examples are
hashed, but complete installed dependency-binary provenance is still required.

Timings are local observations, including native process startup. No controlled
performance-regression or four-node scaling acceptance is inferred. Reports remain
`qualification_status=incomplete` until independent/measured, Linux/MPI,
clean-machine/private-CI and broader physics gates are separately satisfied.
