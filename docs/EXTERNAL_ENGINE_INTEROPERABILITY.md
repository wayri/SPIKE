# External Engine Interoperability

## Purpose and current status

SPIKE external-engine adapters provide offline, inspectable handoffs to locally
installed engineering tools. They do not make those engines part of SPIKE's
native solver catalog and do not promote external output to validated results.
Every adapter must preserve explicit geometry, ports, units, assumptions,
artifacts, and provenance across the process boundary.

The implemented boundary is `python/spike_core/external_engines.py`. It exposes
the `spike/external-engine-catalog/v1`,
`spike/external-engine-job/v1`, and `spike/external-result/v1` contracts through
the Python worker. The desktop External Engines center detects local engines and
drives the supported prepare/run workflow.

## Operational matrix

| Engine | Discovery | Case/export | Execution/import | Current status |
|---|---|---|---|---|
| openEMS | Executable discovery plus isolated Python/native-object smoke probe | Implemented | S-parameters and NF2FF field/directivity/power normalization | Reference-validated for the pinned simple-patch fixture; arbitrary boards remain unvalidated |
| ngspice | Executable discovery | Existing explicit-netlist adapter | Existing DC/AC/transient adapter | Separate circuit workflow |
| FastHenry | Executable discovery | Adapter pending | Importer pending | Detection/catalog only |
| FastCap | Executable discovery | Adapter pending | Importer pending | Detection/catalog only |
| OpenFOAM | Executable discovery | Validated multi-region generator pending | External execution remains gated | Thermal architecture target |

Catalog capabilities are adapter-scoped and list only behavior implemented by
the SPIKE adapter, not every capability of the underlying engine. `state` and
`actions` remain the execution gates for entries whose adapters are pending.
For example, the openEMS entry advertises single-excitation S-parameters and
NF2FF only when the compatible runtime is available. Reference validation is a
separate version-bound property and is not a compliance claim.

## Adapter workflow

```text
DesignIR + AnalysisSpec
  -> engine discovery and capability state
  -> adapter-specific preflight
  -> normalized solver geometry and object map
  -> private per-user job directory with a UUID name by default
  -> inspectable exported driver and engine input artifacts
  -> trusted adapter source sent to `python -I -` over stdin
  -> bounded logs and normalized result
  -> provenance, visualization, comparison, and report consumers
```

External engines are never downloaded implicitly. Developer-runtime detection
checks configured runtime paths and `PATH`. Merely opening a project cannot
install or execute an engine. Binary signatures and administrator allowlists
remain production-packaging gates rather than current discovery guarantees.

## CLI surface

The implemented headless commands are:

- `spike accelerators`: list assembly and sparse acceleration backends;
- `spike external-engines`: list external-engine state, actions, and adapter
  capabilities;
- `spike openems-prepare REQUEST [--case-dir DIR]`: preflight and write an
  inspectable case. Mesh resolution and maximum solver time have explicit CLI
  options;
- `spike openems-run CASE [--setup-only] [--timeout-seconds N]`: build the
  CSXCAD setup or explicitly execute a prepared case.
- `spike openems-benchmark [--mesh-resolution-mm 5 4 3]`: execute the official
  simple-patch fixture and report a three-level resonance/directivity
  convergence decision. This is an intentionally expensive real-solver test.

The commands use the same worker contracts as the desktop. They do not bypass
preflight, install dependencies, infer ports, or promote result validity.

## Job and artifact contracts

An openEMS case prepared by the current adapter contains:

```text
job.json
geometry.json
object-map.json
artifacts.json
engine-input/
  run_openems.py
  spike-openems.xml        # after setup execution
engine-output/
  normalized-result.json  # after successful setup/run
  simulation/              # raw openEMS artifacts after a full run
logs/
  openems.log
```

`job.json` records the engine descriptor, complete `AnalysisSpec`, options,
preflight result, job ID, and versioned file map. `artifacts.json` records the
adapter version, byte size, and SHA-256 digest of prepared input artifacts.
`object-map.json` maps tracks, zones, vias, pads, and components back to DesignIR
IDs and records the XY/+Z coordinate convention, millimetre source units, and
scale to metres.

When no `--case-dir` or `output_dir` is supplied, SPIKE creates a UUID-named
directory under the current user's application state:

- Windows: `%LOCALAPPDATA%/SPIKE/jobs/openems/<uuid>`;
- macOS: `~/Library/Application Support/SPIKE/jobs/openems/<uuid>`;
- Linux: `${XDG_STATE_HOME:-~/.local/state}/spike/jobs/openems/<uuid>`.

The UUID is independent of an untrusted analysis ID. POSIX directories are
created with owner-only mode `0700`; Windows uses the per-user Local AppData
location and inherited ACLs.

`engine-input/run_openems.py` is an inspectable export for review and
reproduction. It is not the executed program. At run time SPIKE reads the
trusted payload from `python/spike_core/openems_adapter_source.py`, verifies that
the prepared job names the same adapter-source revision, authenticates the job
and geometry, and embeds those verified in-memory snapshots into the trusted
source sent to an isolated Python interpreter over stdin. The child does not
reopen mutable `job.json` or `geometry.json`. Editing the exported driver or
changing case inputs after launch therefore cannot change what that run executes.

Comparison files and aligned field maps remain downstream work; they are not
created by the current openEMS adapter.

## openEMS discovery

The adapter discovers the `openEMS` executable through `PATH` and optionally
`OPENEMS_INSTALL_PATH`. Execution requires compatible `CSXCAD` and `openEMS`
Python interfaces. By default those interfaces are probed in the SPIKE worker
Python; `SPIKE_OPENEMS_PYTHON` can point to a configured compatible
Python executable. The isolated smoke probe imports both interfaces, constructs
an `openEMS` native object and `ContinuousStructure`, and attaches the structure
to the solver object. A successful import without native-object construction is
not enough.

States are explicit:

- `reference_validated`: the Python/native-object smoke probe succeeds and the
  exact engine/adapter pair matches the packaged patch-antenna convergence
  evidence. Execution is eligible, but arbitrary-board accuracy remains
  unvalidated.
- `experimental`: the probe succeeds but no matching reference record exists;
  prepare, setup, run, and result-import actions are exposed without validation.
- `installed_interface_missing`: an executable was found but compatible Python
  interfaces were not; geometry can be prepared for review but execution is
  blocked.
- `unavailable`: no usable installation was found; case preparation remains
  possible, execution is blocked.

The adapter never invokes `pip`, a package manager, or a network installer.

## openEMS preflight gates

Case preparation requires:

- at least one explicitly selected complete net;
- conductor geometry belonging to the selected net or nets;
- a physical stackup;
- at least one identified copper layer and a valid mapping from every selected
  geometry layer to that copper stackup;
- relative permittivity for every exported dielectric layer;
- finite positive layer thicknesses, conductor properties, dielectric loss,
  and non-degenerate selected conductor coordinates and dimensions;
- finite positive increasing start/stop frequencies and a bounded finite output
  point count (currently 2 through 100,000 points);
- a rigid board. Rigid-flex flattening and bent geometry are unsupported.

Adapter options are also validated before a case is written: mesh resolution
must be finite and within its supported bounds, maximum solver time must be
between one second and seven days, and thread count must be between zero
(automatic) and 1,024. Boundary conditions, mesh growth, end criterion,
reference impedance, via plating, air padding, and verbosity are range checked.
SPIKE estimates FDTD cell count and memory before launch using a conservative
256-byte-per-cell assumption. The default limits are 25 million cells and
8 GiB, with hard configuration ceilings of 200 million cells and 64 GiB. Port
extents are included in that estimate.

Solving additionally requires explicit ports in
`AnalysisSpec.options.ports`. Each port must provide 3D `start` and `stop`
coordinates, direction, reference impedance, and excitation state. Exactly one
port must be excited for each run. SPIKE does not infer ports from selected
pads, connectors, sources, loads, probes, or net endpoints. A case without
ports can be prepared and inspected, but it cannot run.

Port coordinates must be two distinct finite 3D points, direction must be `x`,
`y`, or `z`, and impedance must be finite and positive. Both endpoints must
intersect exported conductor geometry and terminate on distinct selected nets.
These checks happen in preflight rather than being delegated to openEMS.

The current desktop External Engines center submits an empty port list and does
not yet contain a port editor. Consequently it supports preparation and
setup-only inspection, while its full Run action remains gated. The worker
contract accepts explicit ports for integration and test clients; a production
desktop port-definition workflow is still required.

Custom pad shapes produce an approximation warning. Every case also carries
`OPENEMS_TRANSLATION_EXPERIMENTAL`; mesh, ports, translated geometry, and
boundaries require engineering review before interpreting a result.

## Current openEMS translation

The trusted adapter payload, also exported as an inspectable generated driver,
currently maps:

- selected tracks to rectangular conductor polygons;
- selected zones to source polygons;
- pads to rectangles or 32-point elliptical approximations on their declared
  copper layers;
- vias to cylindrical plating shells between declared layer elevations;
- copper layers to conducting sheets using thickness and conductivity;
- dielectric stackup intervals to material boxes using relative permittivity
  and loss tangent;
- explicit ports to openEMS lumped ports;
- frequency, PML boundary defaults, air padding, mesh resolution, mesh growth,
  end criteria, thread count, and maximum solver time to case options.

The automatic mesh starts from selected geometry, stackup elevations, dielectric
wavelength, and bounded air padding. It is a starting configuration, not a
mesh-convergence result. Curved/custom copper, antipads, solder mask, component
packages, connector launches, material dispersion beyond the supplied scalar
properties, and rigid-flex geometry are not translated faithfully.

## Result semantics

Setup-only execution writes the CSXCAD XML and a normalized result with
`status: setup_completed`. A full run computes the configured frequency vector
and port-reflection/transmission columns relative to the single excited port.
Both setup and full-run records use `model_status: approximate`.

Normalized JSON is parsed without accepting `NaN` or `Infinity`. The importer
checks engine ID, status, model status, mesh metadata, existing contained
artifact paths, the exact requested frequency grid, expected single-excitation
S-parameter columns, array shapes, and finite real/imaginary values before
exposing a result. A per-run nonce, job ID, authenticated-input digest, sweep,
and mesh binding prevent stale or unrelated output from being imported.

The imported result records engine and adapter versions, job ID, execution
duration, case path, and SHA-256 of the Python executable. Raw openEMS simulation
files remain in the job directory. Current output does not establish mesh
convergence, port calibration, passivity, causality, energy closure, far-field
accuracy, or correlation with measurements/commercial tools.

Therefore openEMS remains experimental/approximate. It must not be described as
a validated SPIKE full-wave solver or used for compliance sign-off without an
independent validation record.

## Process isolation and limits

The desktop launches the SPIKE worker outside the WebView. The worker launches
a configured Python runtime with the fixed vector
`python -I - --job <case> [--setup-only]`, `shell=False`, the job directory as
its working directory, and a reduced environment. Trusted adapter source is
provided over stdin. The mutable driver exported in the job directory is never
executed. Isolated mode also prevents job-local modules from shadowing standard
or installed modules.

Current bounds are:

- 4 MiB maximum job JSON and 512 MiB maximum authenticated geometry/execution
  snapshot; byte limits are enforced before JSON parsing or hashing;
- 256 MiB maximum normalized result size;
- 8 MiB persisted combined stdout/stderr log; subsequent output is drained but
  not written, and provenance records truncation;
- 16 GiB monitored `engine-output` quota; crossing the quota terminates the
  process tree;
- adapter execution timeout clamped between 10 seconds and seven days; timeout
  terminates the process tree.

Process-tree termination uses `taskkill /T /F` on Windows and a dedicated
process group plus `SIGKILL` on POSIX, with direct-process kill as a fallback.
This covers timeout and output-quota enforcement. Explicit user cancellation is
still pending, as are Windows Job Object hard memory limits and equivalent hard
resident-memory controls. The 16 GiB limit is an output quota, not a RAM limit.

## Security, packaging, and licensing

- No engine or accelerator is downloaded implicitly.
- The current developer runtime discovers configured local installations; it
  does not authenticate third-party binaries or native Python modules.
- Project content does not select an arbitrary executable; the adapter resolves
  its configured local engine/Python runtime and generates the driver.
- Generated paths are resolved and checked against the private job directory.
  The prepared job records the trusted adapter-source SHA-256. Job metadata and
  normalized geometry are authenticated with an HMAC key stored outside the
  case directory in SPIKE's private per-user application-state directory, and
  are revalidated immediately before execution. No key is written beside an
  arbitrary case parent. Edited or copied cases without matching installation
  state must be prepared again.
- The HMAC protects against case-directory edits and accidental corruption. It
  is not a defense against compromise of the same user account or SPIKE state.
- SPIKE executes the trusted source from
  `python/spike_core/openems_adapter_source.py` over isolated stdin. The exported
  `run_openems.py` is never an execution authority.
- Engine logs are artifacts and must not be interpreted as trusted HTML.
- Bundling or redistributing an engine requires a current license, platform,
  export-control, and maintenance review.
- Production bundles must add signed manifests or administrator allowlists
  before claiming authenticated third-party engine discovery.
- openEMS is GPL-3.0-or-later; the SPIKE adapter remains MIT. Distribution must
  preserve the applicable license boundary and notices.

## Validation requirements

`tests/python/test_external_engines.py` covers catalog scoping, reproducible job
and object-map creation, frequency/geometry/stackup/layer preflight failures,
port-to-conductor anchoring, resource bounds, path containment, UUID-based
default jobs, authenticated snapshot execution over isolated stdin, stale-result
binding, bounded strict JSON reads, resistance to job-local import shadowing,
and refusal to spawn an unavailable engine. CLI tests cover catalog and
case-preparation commands. This is a capability-oriented description rather
than an exact test count, and these remain adapter-contract tests rather than
electromagnetic validation.

Release qualification requires canonical transmission-line, via-transition,
port, cavity, antenna, lossy-material, mesh-refinement, and measured-fixture
comparisons. Reports must distinguish independent validation, cross-solver
agreement, external result only, and incomparable configurations.

## Planned adapters

FastHenry and FastCap should reuse the versioned job, object-map, artifact,
timeout, and normalized-result rules. OpenFOAM should use the same process
boundary once its multi-region case generator passes thermal fixtures. Blender
remains an export/visualization target rather than a solver and must never be
re-imported as authoritative analysis geometry without separate validation.

sparseLizard is a GPL-2.0-or-later C++ FEM library rather than a documented
general-purpose solver executable. SPIKE only discovers/registers its source,
library, or an exact `spike-sparselizard-adapter` candidate; all states remain
adapter-pending and expose no runnable capability. The future adapter must be a
separately licensed fixed process executable with signed-manifest/digest and ABI
provenance, Gmsh volume-mesh input, normalized field/result output, and bounded
allowlisted tuning. SPIKE will not execute arbitrary `slexe` binaries, load the
library into Tauri/Python, use project-compiled formulations, or treat upstream
examples as PCB validation. See `docs/SOLVER_MANAGER.md`.
