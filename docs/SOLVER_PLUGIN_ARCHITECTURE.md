# Solver Plugin Architecture

## Boundary

All numerical engines run behind `spike/solver-plugin/v1`. The application
selects an engine from a machine-readable catalog, builds
`spike/solver-geometry/v1`, and receives `spike/v1` results. Solvers do not read
KiCad files, UI state, or SPIKE project packages directly.

The extension SDK additionally publishes a fixed-argv runtime probe, a
job-relative process job/result envelope, and a solver-neutral mesh artifact:
`spike/solver-plugin-probe/v1`, `spike/solver-plugin-job/v1`,
`spike/solver-plugin-result/v1`, and `spike/solver-mesh/v1`. These contracts
carry digest-bound inputs, object ownership, unit/coordinate metadata, result
artifact hashes, resource ceilings, and adapter provenance. They do not make
an unqualified engine eligible for an analysis.

```text
DesignIR + AnalysisSpec
  -> geometry/material/terminal normalization
  -> capability and validity selection
  -> solver plugin request
  -> engine-specific mesh or circuit model
  -> AnalysisResult + provenance + validation metadata
```

The geometry handoff contains coordinate and unit definitions, complete-net
bundles, tracks, zones, pads, vias, layer stack, dielectric properties,
components, connectors, sources, loads, ports, probes, mesh controls,
frequency controls, and engineering limits. An engine may reject geometry it
cannot model; it must not silently discard it.

## Engine Roles

| Plugin | Intended role | Current state |
| --- | --- | --- |
| `spike.routed_dc` | Resistive routed-copper DC checks | Available, approximate |
| `spike.peec_2_5d` | Quasi-static hybrid-copper PEEC RL extraction | Experimental |
| `spike.mom_surface` | Surface-current and radiation-oriented Method of Moments | Unavailable |
| `spike.fullwave_3d` | Volumetric FEM/FDTD-class structures, enclosures, transitions, antennas | Unavailable |
| `spike.ngspice` | Circuit/network DC, AC, and transient co-simulation | Optional adapter; requires ngspice |
| `external.fasthenry` | Independent quasistatic R/L and impedance comparison | Post-core adapter |
| `external.fastcap` | Independent capacitance-matrix comparison | Post-core adapter |
| `external.openems` | Experimental PCB setup and single-excitation S-parameter comparison | Experimental external adapter; capability-gated |
| `external.openfoam` | Conjugate thermal and airflow comparison/execution | Thermal phase adapter |

The automatic selector considers analysis mode, requested formulation,
required capabilities, plugin state, and priority. Explicit selections are
still checked for compatibility. Only `available` and `experimental` plugins
can execute.

## Process Plugins

A process plugin is installed in a dedicated directory:

```text
solver-id/
  solver-plugin.json
  bin/solver(.exe)
```

SPIKE invokes the fixed entry point without a shell, creates a private job
directory, writes a versioned request file, applies time and output limits, and
validates the result contract. Entry points cannot escape the plugin directory.
Production packaging must additionally verify a signed bundle manifest before
registering a process plugin.

Engine-specific mesh files, restart databases, and logs remain artifacts of the
plugin job. They do not become fields in DesignIR. Result provenance records the
plugin ID/version, formulation, geometry contract, assumptions, convergence,
and engine version.

External engines use the same process isolation and job-directory rules. An
adapter translates `spike/solver-geometry/v1` into an engine-native case and
must write an object map from each exported conductor, dielectric, terminal,
port, thermal region, and boundary back to its DesignIR ID. Imported results
without complete coordinate, unit, and object-map metadata may be retained as
artifacts, but cannot be overlaid or used for automated validation.

## Clean-Room External Adapter SDK

`solver_sdk/` contains schema-validated, fail-closed descriptors for openEMS,
Elmer FEM, and sparseLizard. They are public-API integration blueprints, not
bundled engines or adapters: each remains `unavailable` until a local runtime
is detected by a fixed probe, the exact translator/importer passes its own
fixture, and the requested workflow passes its qualification gate. A positive
probe records only runtime/adapter evidence; it cannot change a PCB result to
validated or compliant.

The openEMS blueprint follows the public Python/CSXCAD interface (explicit
ports, FDTD setup/run, and NF2FF capabilities). The Elmer and sparseLizard
blueprints similarly name only public executable/API boundaries. No vendor or
third-party implementation source is copied, translated, vendored, linked, or
loaded in-process by these descriptors.

External comparison and external execution are separate capabilities:

- A `validation_reference` adapter compares an existing SPIKE result against
  an independently generated external result.
- A `production_solver` adapter may supply the active result only after its own
  accuracy, packaging, security, and license gates pass.
- Running two adapters over the same approximation is not independent
  validation and must be identified as a consistency check.

## Validation Gates

Each engine and formulation needs independent fixtures and thresholds:

- DC: analytical resistor networks, current continuity, voltage-drop and loss
  conservation, mesh refinement.
- 2.5D PEEC: stripline/microstrip, loop and via inductance, plane impedance,
  frequency-validity and conditioning limits.
- Surface MoM: canonical conductor current and radiation fixtures, mesh order,
  port normalization, reciprocity and energy balance.
- Full-wave 3D: waveguide, cavity, via transition, differential channel and
  antenna fixtures, adaptive convergence, boundary and port sensitivity.
- SPICE: upstream regression subset, extracted RLC networks, deterministic raw
  output, convergence and timestep warnings.
- FastHenry/FastCap: canonical conductor fixtures, matrix ordering, conductor
  coverage, unit normalization, discretization refinement, symmetry, and
  comparison against analytical references.
- openEMS: ports, boundary conditions, dispersion, mesh resolution, energy
  balance, S-parameter normalization, and canonical waveguide/antenna/channel
  fixtures.
- OpenFOAM: mesh quality, residual history, mass/energy conservation, thermal
  boundary sensitivity, fan curves, and analytical or measured enclosure
  fixtures.

Catalog state is separate from model status. An installed engine may be
`available`, while a particular result is `Validated`, `Approximate`,
`Unsupported`, or `Failed to converge`.

## ngspice Strategy

The initial adapter uses ngspice as an isolated batch process with explicit
netlists, disabled user initialization, bounded execution, and parsed raw
results. The next integration can use the official shared-library interface
when interactive stepping or parameter updates justify the additional ABI and
threading work.

SPIKE should not create a private ngspice fork now. The differentiating work is
geometry extraction, parasitic model generation, partitioning, model
management, automated setup, sweeps, diagnostics, and reproducible reports.
Fixes to the circuit kernel should be contributed upstream where practical.
A fork is justified only by measured requirements that cannot be implemented
through adapters or accepted upstream, and only after a source-level license
and long-term maintenance review.

## Near-Term Work

1. Add progress, cancellation, artifact streaming, and per-job memory limits.
2. Add scalable partial-inductance acceleration with explicit error bounds.
3. Add capacitance and loss models, then correlate against measured fixtures.
4. Select and license-review candidate MoM and full-wave engines.
5. Expose benchmark history and convergence evidence in desktop diagnostics.
6. Implement the post-core external-engine adapters described in
   `EXTERNAL_ENGINE_INTEROPERABILITY.md` only after PI, thermal, and SI gates.
