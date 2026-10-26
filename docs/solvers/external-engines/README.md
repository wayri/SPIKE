<!-- SPDX-License-Identifier: Apache-2.0 -->
# External solver and engineering-engine status

SPIKE separates runtime discovery, adapter verification, reference validation,
product validation, and compliance assessment. Finding an executable or
completing an adapter smoke test does not establish physics accuracy. The
authoritative deployment policy and the dated development-workstation snapshot
are in [`EXTERNAL_SOLVER_DEPLOYMENT.md`](../../EXTERNAL_SOLVER_DEPLOYMENT.md).


Completion labels describe bounded implementation, not physical or release
qualification. See [all capability completion states and remaining work](../completion.md).

## Additional completion states

| Solver or supporting workflow | Completion state |
| --- | --- |
| PALACE | Workbench implemented; live native accuracy unverified |
| Xyce | Workbench implemented; live native accuracy unverified |
| sparseLizard production PCB adapter | Partial adapter infrastructure; required executable unavailable |
| Elmer FEM | Planned / unavailable example descriptor |
| FreeCAD | Implemented bounded geometry exchange; not a physics solver |
| Siemens FloTHERM | Planned / no adapter |

## Executable adapters with bounded workflows

| Engine | SPIKE path and present state | Main limits and setup | Completion state |
| --- | --- | --- | --- |
| openEMS / CSXCAD | Authenticated prepare/run/import, explicit ports, S-parameter normalization, NF2FF, desktop inspection; the pinned simple-patch pair is reference validated. | Install the isolated pinned runtime. Arbitrary PCB and EMC-compliance claims remain unvalidated. See [`PI_SI_OPENEMS_TUTORIAL.md`](../../PI_SI_OPENEMS_TUTORIAL.md), [`openEMS reference evidence`](../../validation/OPENEMS_REFERENCE_VALIDATION.md), and the [extension README](../../../extensions/openems_suite/README.md). | External integration; runtime-dependent |
| EMerge | Executable extension workflows for bounded electromagnetic preparation and retained results, with version-gated support. | Scope and supported runtime pairs are defined in [`EMERGE_VERSION_SUPPORT.md`](../../EMERGE_VERSION_SUPPORT.md); co-simulation handoff limits are in [`EMERGE_COSIMULATION.md`](../../EMERGE_COSIMULATION.md) and [release evidence](../../validation/EMERGE_RELEASE_INTEGRATION_20261023.md). See the [extension README](../../../extensions/emerge_suite/README.md). | External integration; runtime-dependent |
| SU2 | Experimental generated airflow and planar three-zone CHT cases with fixed inputs, bounded execution, convergence classification, and strict result import. | Runtime must be installed separately. These cases do not establish general assembly CFD, turbulence, radiation, buoyancy, contacts, or production CHT. See [`SU2_AIRFLOW.md`](../../SU2_AIRFLOW.md), [`SU2_CHT.md`](../../SU2_CHT.md), and [native execution evidence](../../validation/NATIVE_SU2_CFD_20261011.md). | External integration; runtime-dependent |
| OpenFOAM | Experimental bounded single-region and separate multiregion solid/fluid execution with field import; retained synthetic fan CHT and solid-only radiation cases exist. | The dated workstation record observed v2606 under Ubuntu WSL. General imported-assembly CHT, paired interface-flow histories, independent comparison and measured correlation remain open. See [current status](../../SOLVER_STATUS.md), [fan qualification](../../FAN_CHT_QUALIFICATION.md), [cooling evidence](../../validation/THERMAL_COOLING_ENVIRONMENTS_20261009.md) and [`OPENFOAM_FAN_BOUNDARIES.md`](../../OPENFOAM_FAN_BOUNDARIES.md). | External integration; runtime-dependent |
| CalculiX | Experimental separately installed CalculiX thermal adapter for admitted tetrahedral assembly problems, including declared boundary conditions and retained contacts. | No solved fluid, nonmatching/moving contact, or inferred component physics; exact supported case scope follows the adapter contract. See [`CALCULIX_THERMAL.md`](../../CALCULIX_THERMAL.md), [extension README](../../../extensions/calculix_suite/README.md), and [focused evidence](../../validation/THERMAL_COMPONENT_CALCULIX_20261006.md). | External integration; runtime-dependent |
| Gmsh | Separately installed geometry/mesh extension with bounded contracts; it prepares simulation geometry rather than validating downstream physics. | Discovery and a successful mesh do not validate a solver model. See the [extension README](../../../extensions/gmsh_suite/README.md) and [`EXTERNAL_SOLVER_PLUGIN_GUIDE.md`](../../EXTERNAL_SOLVER_PLUGIN_GUIDE.md). | External integration; runtime-dependent |
| ngspice | Existing explicit-netlist circuit execution and staged PEEC hybrid workflow. | Runtime discovery exists; end-to-end device-model and coupled-product qualification remain model specific. See [`PEEC_NGSPICE_HYBRID.md`](../../PEEC_NGSPICE_HYBRID.md). | External integration; runtime-dependent |

All external processes remain outside the desktop process. A project request
must not supply arbitrary shell commands, executable arguments, plugins, or
unbounded file references. Runtime identity, input/output digests, units,
cancellation, and result admission remain part of each adapter contract.

## Experimental native workbenches

PALACE and Xyce have dedicated workbenches for authoring, admission, private-job
execution, cancellation, and bounded output inspection. Their runtimes are not
bundled. Neither live runtime was available for the recorded workbench accuracy
comparison, so adapter and UI tests do not establish native numerical accuracy,
MPI, GPU execution, or automatic circuit/field coupling.

- PALACE accepts an explicit native configuration and mesh path; supported
  problem families include driven, eigenmode, transient, electrostatic,
  magnetostatic, and boundary mode. The current launcher is serial and rejects
  explicit MPI/thread allocation beyond its admitted setting. See the
  [PALACE extension README](../../../extensions/palace_suite/README.md).
- Xyce accepts a constrained netlist and safe relative text-library includes,
  validates native syntax, and imports finite CSV waveforms. Arbitrary options,
  plugins, MPI launchers, and outside references are rejected. See the
  [Xyce extension README](../../../extensions/xyce_suite/README.md).

The shared workflow and project persistence rules are in
[`PALACE_XYCE_WORKBENCHES.md`](../../PALACE_XYCE_WORKBENCHES.md).

## Adapter contracts present, production engine unavailable or unqualified

### sparseLizard

SPIKE implements deterministic case preparation, a fixed process protocol,
process-tree cancellation, result normalization, signed staging/rollback tools,
and qualification reporting. The production PCB adapter executable is absent;
a legacy native self-test runtime does not enable PCB solving. The optional
PETSc/MUMPS backend is also a single-process `COMM_SELF` path until separately
provisioned and qualified.

Run must fail closed unless the exact `spike-sparselizard-adapter` executable,
case digests, output bounds, and result contract pass. Required promotion
evidence covers DC, AC/RLCG, thermal, electrostatic, and harmonic-field fixtures.
See [`SPARSELIZARD_ADAPTER.md`](../../SPARSELIZARD_ADAPTER.md) and
[`SPARSELIZARD_NATIVE_WINDOWS.md`](../../SPARSELIZARD_NATIVE_WINDOWS.md).

### Elmer FEM

The extension SDK contains an intentionally unavailable example descriptor and
a documented translation blueprint. It is not an installed executable adapter
or a validation claim. Activation requires a verified fixed entry point,
ElmerGrid/solver-input translation, bounded process execution, normalized
result import, and named qualification fixtures. See
[`EXTERNAL_SOLVER_PLUGIN_GUIDE.md`](../../EXTERNAL_SOLVER_PLUGIN_GUIDE.md).

## Geometry and model-exchange tools

FreeCAD is an ECAD/MCAD exchange workbench, not a solver qualification route.
The recorded headless kernel smoke imports four solids, checks positive volume,
and exports two mechanical objects. This validates the bounded exchange path
only. Geometry exchange does not establish thermal contact, fluid-domain or
mechanical-model qualification. Supported round-trip details follow
[`FREECAD_COLLABORATION.md`](../../FREECAD_COLLABORATION.md); do not infer a
general MCAD authoring or validated assembly-simulation product from that smoke.

## Planned licensed connector

Siemens FloTHERM is not detected and SPIKE has no adapter. Any future integration
must be an optional customer-supplied licensed connector through a permitted
Siemens ECXML, documented API, or export workflow. SPIKE must not bundle,
download, activate, or bypass licensing, and a connector would need explicit
unit, material, boundary-condition, version, entitlement-state, provenance, and
comparison evidence. The independent OpenFOAM route remains separate. See the
FloTHERM policy in
[`EXTERNAL_SOLVER_DEPLOYMENT.md`](../../EXTERNAL_SOLVER_DEPLOYMENT.md#flotherm-and-commercial-solvers).

## Scheduling and acceleration boundaries

The independent worker pool currently admits only its fixed internal-operation
allowlist; it does not automatically schedule these external engines. External
adapters have their own process bounds and runtime requirements. GPU discovery
or an available CUDA sparse backend likewise does not imply openEMS, EMerge,
PALACE, Xyce, SU2, OpenFOAM, CalculiX, Gmsh, ngspice, sparseLizard, Elmer, or
FreeCAD uses that GPU path. Cross-node GPU allocation and distributed
single-solve MPI orchestration remain unsupported. See the
[`execution and acceleration overview`](../execution/README.md).
