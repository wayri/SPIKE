# SPIKE Solver Plugin SDK

For the illustrated, end-to-end authoring and qualification walkthrough, see
[`docs/EXTERNAL_SOLVER_PLUGIN_GUIDE.md`](../docs/EXTERNAL_SOLVER_PLUGIN_GUIDE.md).

Solver plugins consume normalized geometry and analysis intent. They do not
parse KiCad, control the desktop UI, or write directly into a SPIKE project.

## Contracts

- Manifest: `spike/solver-plugin/v1`
- Runtime probe request/result: `spike/solver-plugin-probe/v1` / `spike/solver-plugin-probe-result/v1`
- Process job/result artifacts: `spike/solver-plugin-job/v1` / `spike/solver-plugin-result/v1`
- Solver-neutral mesh artifact: `spike/solver-mesh/v1`
- Full design geometry: `spike/v1`
- Isolated electrical geometry: `spike/net-geometry/v1`
- Analysis request: `AnalysisSpec` in `spike/v1`
- Result: `AnalysisResult` in `spike/v1`

`AnalysisSpec` selects a plugin using `solver_id`, `formulation`, and
`required_capabilities`. `auto` selects the highest-priority available plugin
that satisfies every requirement.

For a user-selected engine, the solver manager resolves the exact declared ID
or returns a blocked selection. It never silently substitutes another engine.
An extension must not expose itself as runnable merely because a descriptor is
present on disk.

## Runtime, Mesh, And Result Exchange

A process descriptor supplies fixed probe arguments (no shell), bounded probe
time, supported mesh contracts, and a job-relative output path. SPIKE writes
the generic job manifest, verifies every input artifact digest and containment,
then launches the adapter. The adapter returns only bounded, job-relative
result artifacts carrying SHA-256, size, contract, adapter version, and probe
state. The owning workflow validates/normalizes those artifacts before display
or use; a plugin result is not automatically an `AnalysisResult`.

`solver-plugin.example.json` is a generic template. The openEMS, Elmer FEM,
and sparseLizard files are deliberately unavailable clean-room examples. They
document public-API adapters and the required gates, but contain no vendor
code, executable, package installer, or activation behavior.

A passed runtime probe establishes only that the fixed adapter can talk to one
identified local runtime. Adapter fixture validation, workflow applicability,
convergence, independent or measured correlation, and compliance remain
separate gates.

## Process Plugin Layout

```text
solvers/
  vendor.engine/
    solver-plugin.json
    solver-engine.exe
    LICENSES/
    validation/
```

SPIKE starts process plugins without a shell:

```text
solver-engine --request <job>/request.json --result <job>/result.json
```

The executable runs in a private job directory. It reads only the request and
approved bundled assets, then writes one result JSON file. Large field meshes,
matrices, Touchstone files, and waveforms should be job-relative artifacts
listed in `AnalysisResult`; do not embed unbounded arrays in control messages.

## Required Manifest Claims

Every plugin declares:

- analyses and formulations;
- geometry and result contract versions;
- capabilities used for automatic selection;
- availability and model status;
- validation record and known limits;
- provider, version, license, and packaging status.

An engine is not `validated` merely because it converged. Validation requires
published fixture tolerances and solver-version-specific regression results.

## Security

- An entrypoint cannot escape its plugin directory.
- Commands are fixed argument arrays and never shell strings.
- Request, result, runtime, memory, and artifact sizes are bounded.
- Production discovery is limited to installer-managed, signature-verified
  plugin roots.
- Imported netlists, models, scripts, and meshes are untrusted data.
- Plugins do not receive network access unless a separately declared cloud
  execution policy grants it.

## Current Plugin IDs

- `spike.routed_dc`: available approximate resistive network.
- `spike.peec_2_5d`: C++ kernel exists; DesignIR adapter is pending.
- `spike.mom_surface`: interface reserved; no engine is packaged.
- `spike.fullwave_3d`: FEM/FDTD interface reserved; no engine is packaged.
- `spike.ngspice`: optional process-isolated explicit-netlist adapter.
