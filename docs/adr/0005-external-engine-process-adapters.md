# ADR 0005: External-Engine Process Adapters

- Status: Accepted
- Date: 2026-08-09

## Context

SPIKE needs optional interoperability with full-wave, field, thermal, and
circuit engines without linking every engine into the desktop process or making
their dependencies mandatory. External tools have different licenses,
installation layouts, input formats, output sizes, failure modes, and execution
times. They may crash, hang, emit untrusted logs, or produce results that cannot
be compared directly with SPIKE.

A direct UI-to-executable call would couple presentation code to engine details
and bypass DesignIR, solver validity, process isolation, and reproducibility.
Loading arbitrary project-provided scripts would also create an unacceptable
execution boundary.

## Decision

Implement external engines as offline, versioned process adapters owned by the
Python worker. Each adapter must:

- discover explicitly configured local installations and `PATH` entries
  without downloading anything;
- publish an engine descriptor whose capabilities are limited to implemented
  adapter behavior, with explicit state/action gates;
- validate DesignIR and AnalysisSpec before writing a case;
- create a UUID-named private per-user job directory by default, with versioned
  job, geometry, object-map, artifact, result, and log contracts;
- authenticate execution-relevant job metadata and normalized geometry with a
  per-user key in private SPIKE application state, then repeat physical/resource
  preflight and execute in-memory snapshots of the authenticated inputs;
- generate adapter-owned input and an inspectable exported driver, but execute
  only trusted adapter source supplied to `python -I -` over stdin;
- invoke fixed argument vectors with `shell=False`, a controlled working
  directory, bounded environment, capped logs, timeout, and output limits;
- normalize supported results and preserve raw artifacts and provenance;
- report omitted, approximated, unsupported, and incomparable data explicitly.

openEMS is the first implemented adapter. Its state becomes `experimental` only
when an isolated smoke probe imports openEMS/CSXCAD, constructs their native
objects, and attaches a `ContinuousStructure`. Every current normalized result
is `approximate`. Preparation preflight checks finite increasing frequencies and
frequency points, selected conductor geometry, copper/layer mapping, stackup and
dielectric properties, rigid-board technology, bounded options, estimated cell
and memory budgets, and explicit ports. Port extents contribute to resource
estimates. Solving requires finite, distinct 3D port coordinates anchored to
distinct exported conductors, positive impedance, valid direction, and exactly
one excited port. SPIKE does not infer
ports from pads, probes, connectors, or source/load definitions. The current
importer normalizes setup metadata and S-parameters; field and far-field
normalization remains pending.

Normalized results are bounded strict JSON. Engine identity, status, model
status, a per-run nonce and authenticated-input digest, exact requested
frequency grid, expected port columns, array shapes, finite values, mesh
metadata, and existing artifact-path containment are checked before import.

No external engine is downloaded, installed, or executed implicitly. Case
preparation and execution are separate explicit actions. FastHenry, FastCap,
Elmer, OpenFOAM, ngspice, and future adapters must use the same contract and
security principles even where their current implementation status differs.

Current developer-runtime discovery does not authenticate third-party binaries
or native Python modules. Signed bundle manifests and administrator allowlists
are production packaging gates, not properties claimed by this adapter.

The supported command-line surface is `spike accelerators`,
`spike external-engines`, `spike openems-prepare`, and `spike openems-run`.
These commands use the worker contracts and the same preflight gates.

## Consequences

- Engine failures remain outside the React/WebView process and are bounded by
  the worker and adapter watchdogs.
- Cases can be inspected, archived, reproduced, and executed independently.
- Object maps preserve traceability from engine entities to DesignIR objects.
- Engine and adapter licensing can be reviewed independently from SPIKE core.
- External agreement does not automatically establish independent truth.
- Geometry translation and result normalization must be validated per engine.
- Large raw field results need future chunked/file-backed ingestion rather than
  the current bounded JSON result.
- The prepared job records the trusted adapter-source revision. The runner
  rejects a revision mismatch and executes the in-package source from
  `python/spike_core/openems_adapter_source.py` over isolated stdin, never the
  mutable exported `run_openems.py`.
- Job metadata and geometry are authenticated against per-user installation
  state and revalidated at execution. This detects case-directory edits; it is
  not a same-user compromise boundary.
- Logs are capped at 8 MiB and engine output is monitored against a 16 GiB
  quota. Timeout or quota breach terminates the process tree through Windows
  `taskkill /T /F` or a POSIX process group, with direct kill as fallback.
- Explicit user cancellation and Windows Job Object hard memory limits remain
  pending. The output quota is not a process-memory limit.
- The openEMS adapter does not enable the unavailable native
  `spike.fullwave_3d` solver entry.
- Contract tests describe covered behavior generically and include preflight,
  path containment, UUID job naming, isolated trusted-source execution, and
  unavailable-engine recovery; an exact test count is not an architecture fact.

## Rejected alternatives

- Link all engines into the desktop or Python worker: weakens crash isolation
  and makes optional licenses/dependencies mandatory.
- Let React generate engine files directly: duplicates geometry semantics and
  bypasses service-level validation.
- Execute scripts embedded in a project: creates an arbitrary-code execution
  path.
- Download missing engines on demand: violates offline, security, deployment,
  and administrator-control requirements.
- Infer openEMS ports automatically and run: produces ambiguous excitation and
  reference-plane semantics.
- Label any successful external run as validated: process completion does not
  establish geometry fidelity, convergence, calibration, or accuracy.
