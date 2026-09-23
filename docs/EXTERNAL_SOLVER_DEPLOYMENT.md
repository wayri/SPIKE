# External Solver Deployment And Qualification

## Policy

SPIKE treats installation, execution capability, reference validation, product
validation, and regulatory compliance as separate gates. A detected executable
does not satisfy the next gate automatically.

| Gate | Meaning |
| --- | --- |
| Discovered | A local path or executable was found. Nothing has run. |
| Adapter verified | A bounded native/API smoke probe and contract round trip pass. |
| Reference validated | A pinned engine/adapter pair passes a named fixture and convergence gate. |
| Product validated | The requested geometry/model class has sufficient correlation evidence. |
| Compliance assessed | A documented standard, laboratory method, uncertainty budget, and sign-off apply. |

The UI and reports must retain the narrowest applicable state. An AI-generated
summary cannot promote it.

## Development Workstation Snapshot

This table records the observed workstation state on 2026-08-10. It is not a
portable installation promise; runtime discovery must be repeated on every
machine and packaged release.

| Runtime | Installed | Executable adapter | Qualification |
| --- | --- | --- | --- |
| NumPy/SciPy SuperLU | Yes | Yes | Covered by native regression corpus |
| Numba 0.66.0 | Yes | Yes, assembly only | Numerical-equivalence tests required per release |
| ngspice 46 | Yes | Existing explicit-netlist path | Discovery works; end-to-end device-model qualification remains |
| openEMS 0.0.36 / CSXCAD 0.6.3 | Yes, isolated Python 3.11 runtime | Yes; `reference_validated` is runnable | Simple-patch reference validated; arbitrary PCB/compliance unvalidated |
| FreeCAD 1.1.3 | Yes | ECAD/MCAD exchange workbench | Real headless kernel smoke passes with four solids and two mechanical exports; this validates the exchange path only |
| PETSc/MUMPS | Not asserted by SPIKE | Native sparse adapter exists | Administrator-provided signed bundle and functional registration probe required |
| OpenFOAM v2606 | Yes, Ubuntu 24.04 WSL | Deterministic single-region air case generation, fixed-argv execution/cancellation, and strict T/U/p field import | Real air-domain smoke passes execution/import; PCB solids, CHT, advanced environments, convergence corpus, and external validation pending |
| sparseLizard | Legacy native self-test runtime only | PCB case/result adapter contract implemented; production executable absent | Signed staged adapter, MUMPS-enabled PETSc, and five passing PCB fixture records required |
| FloTHERM | No entitlement detected | No adapter | Licensed Siemens integration and ECXML/API agreement required |

Ubuntu 24.04 is present under WSL. OpenFOAM v2606 and OpenMPI were installed
from the signed OpenCFD Noble repository after explicit administrator approval.
SPIKE discovers `/usr/bin/openfoam2606` through a fixed, no-shell WSL command;
it does not capture or store administrator credentials. Docker Desktop is
installed but its daemon is not running.

## Deployment Matrix

| Tool | Redistribution/deployment policy | SPIKE integration today | Required next qualification gate |
|---|---|---|---|
| openEMS / CSXCAD | Optional pinned offline runtime in an isolated engine-specific Python environment; no implicit network install | Authenticated prepare/run/import adapter, explicit desktop port editor, S-parameter normalization, NF2FF execution, dashboard, and report data | Add representative arbitrary-PCB and measured/chamber correlation; preserve per-board convergence and `not_validated` state until passed |
| OpenFOAM | Target a pinned native Linux, WSL2, or controlled container host outside the desktop process | Experimental steady-state open-air natural/forced convection case, bounded fixed-argv execution, cancellation, convergence classification, and aligned cell-centre T/U/p import | Add and validate PCB solid conduction, CHT, fan curves/geometry, contacts, cabinets, radiation, potting, altitude, vacuum rejection, transient CFD, mesh convergence, and energy balance |
| Siemens FloTHERM | Customer-supplied licensed installation only. Never bundle, download, activate, or bypass licensing without entitlement and permitted automation rights | No connector and no entitlement detected | Define a licensed ECXML/documented-API connector, unit/material/boundary mapping, version/license provenance, result importer, and Siemens-reference comparison suite |
| FreeCAD | Optional LGPL-compatible external application/workbench using inert versioned JSON and STEP/B-Rep references | Workbench scaffold, bounded geometry/mechanical contracts, primitive B-Rep import, envelope/keepout export, and passing local kernel smoke | Add exact board cutouts, placement transforms, rigid-flex regions, contacts, air/potting volumes, enclosure/fan/heatsink objects, and stable round-trip fixture coverage |
| sparseLizard | Separate process adapter; review GPL-2.0-or-later obligations for any linked redistribution | DesignIR case translation, process isolation/cancellation, result normalization, signed staging/rollback scripts, and qualification reporting; production PCB executable absent | Build/sign the fixed-protocol adapter with MUMPS-enabled PETSc, then pass DC, AC/RLCG, electrostatic, harmonic-field, and thermal PCB fixtures |
| PETSc/MUMPS | Linux-first optional worker dependency; record scalar type, MPI, PETSc, MUMPS, and compiler provenance | Single-process `COMM_SELF` sparse solve code exists, but `petsc4py`/MUMPS is not installed in the current worker | Install a pinned runtime and pass SuperLU equivalence, residual, complex-scalar, failure, memory, and large-system performance tests before auto-selection |

No row above promotes an unavailable tool to installed or validated. Discovery,
adapter verification, reference-fixture validation, product validation, and
compliance assessment remain separate states.

## Process-Adapter Extension Contract

The clean-room extension SDK publishes a generic descriptor plus fixed-argv
runtime-probe, digest-bound mesh/job, and result-artifact contracts. The
openEMS, Elmer FEM, and sparseLizard example descriptors are intentionally
`unavailable`: they are not installers, executable adapters, or an assertion
that a runtime is present. A host may activate a descriptor only after it
contains a verified local entry point, its fixed probe returns an expected
versioned response, the adapter owns a safe translator/importer, and its named
fixture/qualification gates pass. Probe success alone is not physics or
product validation.

The openEMS blueprint is based on the public openEMS Python/CSXCAD API
documentation, including its explicit port, run, and NF2FF interfaces. Elmer
FEM and sparseLizard blueprints are restricted to public executable/API
boundaries. SPIKE does not reuse their implementation source or accept a
third-party plugin result without normalized ownership, unit, digest, and
qualification evidence.

## PETSc/MUMPS Deployment Readiness

SPIKE never downloads PETSc or MUMPS. Native Windows and Linux bundles are
provisioned by an administrator and registered through
`scripts/register_petsc_mumps_readiness.ps1`. Registration verifies a
CMS-signed `spike/petsc-mumps-dependency/v1` manifest, hashes every declared
artifact under the supplied PETSc/MUMPS prefixes, and requires a probe to prove
that PETSc registered `MATSOLVERMUMPS` and completed a MUMPS-backed solve. It
then emits a signed `spike/petsc-mumps-readiness/v1` record.

The native sparseLizard Windows installer consumes that passing record before
build, stages and self-tests a replacement bundle, verifies release trust,
signs a v2 runtime manifest, and retains the prior signed release for rollback.
This is deployment evidence only. It neither fabricates PETSc/MUMPS readiness
nor promotes the solver, adapter, or any PCB workflow to validated.

`spike sparselizard-validation-status` evaluates the immutable five-class
qualification plan and evidence directory. A suite can become validated only
when the activated runtime is signed, PETSc reports a functional
`MATSOLVERMUMPS` solve, and all DC, AC/RLCG, thermal, electrostatic, and harmonic
field fixtures pass their declared tolerances. Missing evidence is `blocked`,
not success.

## openEMS Desktop NF2FF Flow

The implemented desktop path is:

1. Select candidate and return nets in the EMI workbench.
2. Define explicit conductor-to-conductor lumped ports with 3D endpoints,
   direction, impedance, and exactly one excitation.
3. Request bounded far-field frequencies, theta/phi grids, observation radius,
   and phase center using `spike/openems-far-field-request/v1`.
4. Preflight conductor coverage, stackup/materials, ports, mesh, boundary
   padding, sample limits, and runtime limits.
5. Prepare an authenticated immutable case and run the trusted adapter in the
   isolated openEMS Python process.
6. Create the NF2FF box after final mesh construction, run FDTD and
   `CalcNF2FF`, and import shape-checked E-field components, angular power,
   directivity, and radiated power.
7. Bind the result to the run ID, input digest, frequency grid, and mesh before
   showing frequency-selectable polar cuts and metrics in the dashboard/report.

The exact openEMS 0.0.36 / adapter 1.1.0 pair is reference-validated for the
named simple-patch fixture and is therefore runnable. That fixture establishes
the tested translation, port, FDTD, normalization, NF2FF, and convergence path
only. Every arbitrary PCB result remains `not_validated` until its own mesh
convergence and independent trusted-solver or measured correlation evidence is
attached. No NF2FF result is an EMC compliance assessment by itself.

## Supported Installation Layout

Third-party engines stay outside the desktop process. Pinned offline runtimes
may live under `runtime/external`, and engine-specific Python environments under
`runtime/envs`. These directories are excluded from source control. The lockfile
records exact versions and SHA-256 hashes for redistributable dependencies.

Production packages must additionally provide:

- an SBOM and license notices;
- binary signatures and publisher verification;
- per-engine process accounts or sandbox rules;
- memory, CPU, output-size, timeout, and cancellation limits;
- deterministic environment variables and no implicit network access;
- rollback and side-by-side runtime versions.

## Linux Solver Host Plan

OpenFOAM, PETSc/MUMPS, and sparseLizard should run behind the same
`spike/external-result/v1` process boundary on native Linux or WSL2. The Windows
desktop must not import their shared libraries directly.

The implementation and qualification sequence is:

1. Install pinned packages into a controlled Ubuntu host after administrator
   approval.
2. Add a host probe reporting distro, package versions, scalar precision, MPI,
   and executable hashes.
3. Implement a signed SPIKE runner with fixed verbs; never accept raw shell
   arguments from a project.
4. Extend the working single-region field importer with OpenFOAM multi-region
   solid/fluid case generation, fan curves, contact resistance, radiation,
   potting regions, altitude-dependent fluid properties, residual histories,
   and energy-balance records.
5. Validate natural convection, forced duct flow, conjugate heat transfer, and
   vacuum rejection independently.
6. Qualify PETSc/MUMPS against SuperLU residuals and large sparse memory tests.
7. Add sparseLizard only after its GPL boundary and process adapter are reviewed.

Official OpenFOAM installation guidance is at
<https://www.openfoam.com/download/openfoam-installation-on-linux>. No runtime
is considered available until SPIKE's probe and fixture suite pass.

## FloTHERM And Commercial Solvers

FloTHERM is proprietary Siemens software. SPIKE cannot bundle, download, or
activate it without a customer license and permitted automation interface.
Integration can only be an optional licensed connector using a Siemens-
documented ECXML/API/export workflow permitted by the customer's entitlement.
SPIKE must not ship Siemens binaries, license files, installers, or activation
logic. The connector must record engine version, entitlement/connection state
without secrets, project units, material mapping, boundary conditions, and
imported-result provenance. The open-core product must continue to provide an
independent OpenFOAM path.

## ECAD/MCAD And FreeCAD

The FreeCAD workbench uses versioned inert JSON contracts. It imports SPIKE
primitives into real B-Rep solids and exports component envelopes/keepouts. The
headless FreeCAD 1.1.3 kernel test imports four solids, verifies positive volume,
exports two mechanical objects, and revalidates the exchange.

The next contract version should add exact STEP/B-Rep references, board cutouts,
component placement transforms, rigid-flex regions, thermal-contact surfaces,
air volumes, heatsinks, fans, enclosure walls, potting volumes, and stable
round-trip IDs. FreeCAD remains the geometry-authoring/inspection host; solver
state stays in SPIKE.

## Environment Profiles

The `spike/environment-profile/v1` contract supplies immutable presets for lab,
potted/sealed, automotive, marine, aerospace altitude, vacuum/space, and user-
defined conditions. Profiles carry domain-specific PI, SI, thermal, and EMI
metadata plus readiness issues. They are engineering input seeds and capability
gates, not geometry, boundary-condition generation, solver validation, product
qualification, or certified environmental standards. Validation reports
certification as `not_assessed` and cannot promote it.

Vacuum profiles reject continuum convection and airflow. Potting profiles carry
both thermal conductivity and dielectric properties. Automotive, marine, and
aerospace qualification still requires the user to name the actual governing
standard, severity, mounting, duty cycle, and acceptance criteria, then attach
solver-appropriate geometry and independently reviewed evidence.
