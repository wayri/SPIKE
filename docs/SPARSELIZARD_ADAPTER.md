# sparseLizard Process Adapter

## Scope

`python/spike_core/sparselizard_adapter.py` defines the SPIKE boundary for a
separately built `spike-sparselizard-adapter` executable. It is not a Python
binding to sparseLizard and does not load a sparseLizard library, source tree,
plugin, or shared object into the SPIKE process.

This separation is required for predictable licensing, crash isolation,
reproducibility, and replacement of the adapter without changing the desktop
application or PDN optimizer.

The native Windows runtime build and its limited DC FEM self-test are described
in `docs/SPARSELIZARD_NATIVE_WINDOWS.md`. A verified runtime is not the process
adapter described here and does not enable PCB solver capabilities by itself.

## Local Discovery

The adapter is runnable only when one of these exact executable names resolves:

- A locally registered `external.sparselizard` path whose filename is
  `spike-sparselizard-adapter` or `spike-sparselizard-adapter.exe`.
- The same exact executable name found on the local `PATH`.

SPIKE does not treat an upstream sparseLizard library, a source checkout, an
arbitrary executable, or an environment root as a runnable adapter. This module
does not download, install, compile, or update sparseLizard.

## Case Contract

`prepare_sparselizard_case()` writes an empty output directory containing:

| File | Purpose |
| --- | --- |
| `geometry.json` | `spike/solver-geometry/v1` DesignIR-derived conductor, stackup, material, and selected-net handoff. |
| `mesh.json` | `spike/sparselizard-mesh/v1` topology-preserving conductor cells, branches, vias, pads, zones, nets, and mesh-quality metadata. |
| `case.json` | `spike/sparselizard-case/v1` request, physics/formulation, materials, terminals, exact frequency grid, reviewed ports, output contract, and SHA-256 bindings. |

The case requires two through 64 differential ports. The first is the reviewed
observation port and the rest are reviewed candidate ports. Every terminal must
identify an existing DesignIR object, object type, and matching net. A port that
is not explicitly reviewed is blocked before a solver process can start.

The adapter invocation is fixed:

```text
spike-sparselizard-adapter run --case <case.json> --output <result.json>
```

The same boundary is available through the local worker and CLI:

```text
spike sparselizard-prepare request.json --case-dir case
spike sparselizard-run case --adapter <exact-adapter-path> --timeout-seconds 3600 --memory-limit-mb 4096
```

Preparation does not require sparseLizard to be installed. Run fails closed if
the exact adapter executable is absent, the prepared files changed, a stale
result exists, the process exceeds a bound, or the returned physics contract is
invalid.

AC multiport `result.json` may use `spike/pi-multiport-result/v1`. DC, thermal,
and field workflows use `spike/sparselizard-pcb-result/v1`; this contract carries
mesh, scalar/vector fields, convergence, issues, and provenance and normalizes
to the common `spike/v1` result envelope. Provenance must carry the exact
`geometry_digest`, `mesh_digest`, and `request_digest` from the prepared case.

## Execution Bounds

`run_sparselizard_case()` uses a separate subprocess with:

- A caller-configured wall-time timeout, default 3600 seconds.
- A caller-configured address-space limit on POSIX hosts and a hard Windows Job
  Object process-memory limit, default 4096 MiB.
- CPU and file-size limits on POSIX hosts.
- Bounded stdout and stderr capture, default 4 MiB each.
- A bounded `result.json`, default 64 MiB.
- A small inherited environment allowlist rather than SPIKE's full process
  environment.

Cancellation, timeout, and stream overflow terminate the complete process tree.
The registered adapter remains a local trusted executable: resource containment
does not sandbox a malicious executable from the operating-system user account.

## Validation Status

Every output is sent through
`external_pi_result_validation.validate_external_pi_multiport`. That validator
requires exact requested frequencies, finite full Z matrices, reviewed ports,
passed convergence evidence, passivity and reciprocity checks, solver and
adapter versions, and provenance. A result may be `validated` or
`reference_validated` only when it supplies explicit validation evidence. SPIKE
does not promote an adapter's status itself.

The normalized result is `spike/pdn-multiport/v1`, which can be consumed by the
solver-independent PDN impedance and capacitor-placement workflow. It is still
the user's responsibility to choose fixtures and validation evidence covering
the intended geometry, frequency range, materials, and operating conditions.

## Adapter Acceptance Gates

Before advertising any sparseLizard capability as validated, add and pass:

1. An adapter build manifest with reproducible version and source revision.
2. Analytical DC resistance, capacitance, inductance, and RLC fixtures.
3. Mesh-convergence records for each supported formulation.
4. Cross-validation or measured fixtures for the advertised operating range.
5. Negative tests for invalid terminal mapping, changed case digests,
   non-passive matrices, incomplete convergence, timeout, and output overflow.
6. Platform smoke tests for Windows and Linux process launchers.

Until those gates are present, the adapter foundation only supports prepared
cases and independently validated result import. It does not claim a validated
PI, SI, thermal, or EMI sparseLizard capability.
