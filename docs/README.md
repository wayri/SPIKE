# SPIKE Documentation Index

Use this page as the entry point for checked-in documentation. Capability and
validation documents describe what exists; planning documents must not be used
as evidence that a workflow is implemented.

Current integration checkpoint: [stability fixes, wave assessment and release
work plan (2026-09-05)](STABILIZATION_RELEASE_PLAN_20260905.md).

## Users and operators

| Need | Start here | Then read |
|---|---|---|
| Complete a desktop task | [User task guide](USER_TASK_SEQUENCES.md) | [Result visualization](RESULT_VISUALIZATION_AND_LIMITS.md), [project format](PROJECT_FORMAT.md) |
| Diagnose a failure | [Troubleshooting](../TROUBLESHOOTING.md) | [Error-code catalog](ERROR_CODE_CATALOG.md), [stability and recovery](STABILITY_AND_RECOVERY.md) |
| Use the CLI | [CLI workflow](CLI_WORKFLOW.md) | [CLI reference](CLI.md) |
| Check solver availability or validity | [Solver status](SOLVER_STATUS.md) | [Validation program](VALIDATION_PROGRAM.md), [release qualification](PI_RELEASE_QUALIFICATION.md) |
| Understand solver mathematics and research provenance | [Solver handbook](SOLVER_HANDBOOK.md) | [Annotated references](SOLVER_REFERENCES.md), [recorded citation inventory](generated/solver-reference-inventory.json) |
| Run SERDES and actuator reference checks | [SERDES reference](SERDES_REFERENCE_QUALIFICATION.md) | [Actuator map review](ACTUATOR_FORCE_MAP.md), [delivery and recent research](SERDES_ACTUATOR_DELIVERY.md) |
| Configure PI | [PI path analysis](PI_PATH_ANALYSIS.md) | [Reference coverage and acceptance](PI_REFERENCE_COVERAGE_20260924.md), [DC solver](DC_SOLVER.md), [transient PI](TRANSIENT_PI.md), [PDN screening](PDN_SCREENING.md) |
| Configure SI/network analysis | [Signal-integrity workbench](SIGNAL_INTEGRITY_NETWORK_WORKBENCH.md) | [Bounded geometry channels](GEOMETRY_DERIVED_SI_CHANNEL.md), [S-parameter integration](SIGNAL_INTEGRITY_NETWORK_INTEGRATION.md) |
| Inspect the circuit language/analysis boundary | [SPIKES language and linear analysis wave 3](SPIKES_LANGUAGE_ANALYSIS_WAVE3.md) | [Solver status](SOLVER_STATUS.md) |
| Inspect nonlinear behavioral analysis | [SPIKES nonlinear language and analysis wave 4](SPIKES_LANGUAGE_ANALYSIS_WAVE4.md) | [Solver status](SOLVER_STATUS.md) |
| Configure thermal work | [Thermal workflow](THERMAL_WORKFLOW.md) | [Transient thermal and viewport](TRANSIENT_THERMAL_AND_VIEWPORT.md) |
| Configure EMI work | [EMI workflow](EMI_WORKFLOW.md) | [Engine gates](SI_SPICE_EMI_RF_ENGINE_GATES.md) |
| Configure loaded SI and model handling | [SI workflow](SI_WORKFLOW.md) | [Solver status](SOLVER_STATUS.md) |
| Use an optional external engine | [External-engine interoperability](EXTERNAL_ENGINE_INTEROPERABILITY.md) | [Deployment](EXTERNAL_SOLVER_DEPLOYMENT.md), engine-specific adapter documents |
| Build a Windows preview installer | [Windows installer](WINDOWS_INSTALLER.md) | [Licensing policy](../LICENSING.md), [release qualification](PI_RELEASE_QUALIFICATION.md) |
| Qualify the packaged Wave 1 assembly | [Wave 1 packaged acceptance](WAVE_1_PACKAGED_ASSEMBLY_ACCEPTANCE.md) | [Project package v3](SPIKE_PROJECT_PACKAGE_V3.md), [Windows installer](WINDOWS_INSTALLER.md) |

The in-app Help Center is the compact operational reference. The checked-in
[user task guide](USER_TASK_SEQUENCES.md) provides longer sequences and uses the same
three reviewed screenshots from `app/public/help`.

## Developers

Read these in order for a new checkout:

1. [Architecture](../ARCHITECTURE.md) for runtime boundaries and dependency
   direction.
2. [Development](../DEVELOPMENT.md) for setup, launch paths, and checks.
3. [Developer guide](DEVELOPER_GUIDE.md) for extension sequences.
4. [Subsystem index](SUBSYSTEM_INDEX.md) for file ownership.
5. [Contracts](CONTRACTS.md), [design principles](DESIGN_PRINCIPLES.md), and
   [language policy](LANGUAGE_POLICY.md) before cross-cutting work.
6. [Engineering governance](ENGINEERING_GOVERNANCE.md) and
   [test fixtures](TEST_FIXTURES.md) before changing numerical behavior.
7. [Research provenance and clean-room engineering](RESEARCH_AND_CLEAN_ROOM_ENGINEERING.md)
   before deriving or qualifying physics from published work.

## Architecture records

| Boundary | Canonical document |
|---|---|
| Runtime and dependency direction | [Architecture](../ARCHITECTURE.md) |
| Design/result contracts | [Contracts](CONTRACTS.md) |
| Import adapters | [Importer architecture](IMPORTER_ARCHITECTURE.md) |
| Solver plugins | [Solver-plugin architecture](SOLVER_PLUGIN_ARCHITECTURE.md) |
| Desktop visualization | [Visualization architecture](VISUALIZATION_ARCHITECTURE.md) |
| Extensions | [Extension architecture](EXTENSION_ARCHITECTURE.md) |
| Proposed FreeCAD assembly and thermal companion | [Extension development plan](FREECAD_ASSEMBLY_THERMAL_EXTENSION_PLAN.md) |
| FreeCAD placement feedback and solid clearances | [Implemented collaboration workflow](FREECAD_COLLABORATION.md) |
| Worker/native desktop | [Native desktop runtime](NATIVE_DESKTOP_RUNTIME.md) |
| Errors and recovery | [Error handling](ERROR_HANDLING.md) |
| Persistence | [Project format](PROJECT_FORMAT.md) |
| Security | [Security model](SECURITY_MODEL.md) |
| Accepted cross-cutting decisions | [Architecture decision records](adr/) |

When these documents disagree, executable contracts and tests identify current
behavior, `SOLVER_STATUS.md` identifies capability status, and the discrepancy
must be corrected rather than resolved by assuming the broader claim.

## Validation and release evidence

- [Validation program](VALIDATION_PROGRAM.md): evidence levels and benchmark
  policy.
- [Validation records](validation/): checked-in inputs, outputs, and focused
  qualification notes.
- [PI release qualification](PI_RELEASE_QUALIFICATION.md): PI release gates.
- [Release runtime qualification](RELEASE_RUNTIME_QUALIFICATION.md): source and
  packaged-worker parity.
- [SPIKES native switching kernel](SPIKES_NATIVE_SWITCHING_KERNEL.md): owned
  PULSE/PWL, breakpoint, and bidirectional-switch implementation boundary.
- [SPIKES competitive gates](SPIKES_COMPETITIVE_GATES.md): fail-closed evidence
  required before parity or superiority claims.
- [Engineering governance](ENGINEERING_GOVERNANCE.md): review and release
  requirements.

An input fixture, screenshot, or passing packaging test is not by itself proof
of arbitrary-board numerical validation.

## Document maintenance

- Keep implemented behavior, planned work, and architecture targets visibly
  distinct.
- Link to an owning source module, contract, fixture, or test for detailed
  implementation claims.
- Add an ADR for a changed process boundary, contract version, persistence
  format, rendering engine, implementation language, or plugin interface.
- Use only reviewed repository assets. Do not add screenshots copied from
  external products or untraceable generated imagery.
- Update `SUBSYSTEM_INDEX.md` when ownership changes.
- Run `python scripts/check_architecture.py` and verify local Markdown links and
  images after documentation changes.
