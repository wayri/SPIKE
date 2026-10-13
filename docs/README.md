# SPIKE documentation

[Solver improvement action plan](SOLVER_IMPROVEMENT_ACTION_PLAN.md): benchmark
feedback, small-signal error tests, thermal/EM accuracy work, coupling validation,
guided setup and performance milestones with explicit completion gates.

[SPIKES sourced parts and interactive workbench](SPIKES_SOURCED_PARTS_WORKBENCH.md):
exact-MPN seed, explicit model readiness, offline curve fitting, plot/dashboard
workflow, captured-limit indications, native KiCad import and wire RLC handoff.

[SPIKES adaptive switching foundation](SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md):
native CLI workflow, stable storage residuals, recovery, reproducible benchmarks
and explicit open converter-qualification limits.

[Co-simulation and digital twins](COSIMULATION_DIGITAL_TWIN.md): experimental
fixed-grid scalar coupling, recorded telemetry comparison, script/CLI workflow
and staged adapter plan.

<img src="../app/public/spike-logo-tagline.png" alt="SPIKE — SI, PI, Thermal, EM" width="420">


Integrated desktop chat: [SPIKE Assistant](INTEGRATED_ASSISTANT.md), including provider consent, reviewed tools and assembly workflows.
[Parallel worker manager](PARALLEL_WORKER_MANAGER.md): local independent-job
pool, protected remote-node enrollment, discovery, limits and diagnostics.

Start with the guides that match what you want to do. [Solver status](SOLVER_STATUS.md)
describes which analyses are available and what their results mean.

See [real board overlays in 2D and 3D](SPIKE_DEMO.md) for native viewport captures
with solved temperature cells and probing.

## Use SPIKE

| Task | Guide |
| --- | --- |
| Try SPIKE in five minutes | [ESP32 quickstart](ESP32_QUICKSTART.md) |
| Import a board and explore the desktop | [User tasks](USER_TASK_SEQUENCES.md) · [Result visualization](RESULT_VISUALIZATION_AND_LIMITS.md) |
| Run power analysis | [PI paths](PI_PATH_ANALYSIS.md) · [DC solver](DC_SOLVER.md) · [Transient PI](TRANSIENT_PI.md) |
| Compare converter losses, return routes and capacitor locations | [PI engineering tools](PI_ENGINEERING_TOOLS.md) |
| Run signal analysis | [SI user guide](SI_USER_GUIDE.md) · [SI workflow](SI_WORKFLOW.md) |
| Author mixed power/signal harnesses and inspect routed conductors | [Harness engineering](HARNESS_ENGINEERING.md) · [Harness DC PI](HARNESS_PI.md) |
| Explore board temperature | [Thermal user guide](THERMAL_USER_GUIDE.md) · [Thermal workflow](THERMAL_WORKFLOW.md) |
| Screen internal channel cooling and check time accuracy | [Internal airflow](INTERNAL_AIRFLOW.md) · [Transient accuracy checks](THERMAL_ACCURACY_CHECKS.md) |
| Couple multiboard PI/SI losses to 3D temperature | [Volume electrothermal setup and results](MULTIBOARD_VOLUME_ELECTROTHERMAL.md) |
| Mesh component STEP solids and link thermal interfaces | [Reviewed component solids and conformal meshing](THERMAL_COMPONENT_SOLIDS.md) |
| Explore antenna and EM results | [EM workflow](EMI_WORKFLOW.md) · [EMerge example](VIRTUAL_EMI_EMERGE_TUTORIAL.md) |
| Mesh a complete planar PCB with local refinement | [Focused volume meshes](PCB_FOCUSED_VOLUME_MESHING.md) |
| Work through examples | [Tutorial atlas](CAPABILITY_TUTORIAL_ATLAS.md) · [ESP32 example](../examples/esp32/README.md) |
| Connect a local language model | [Local LLM and MCP](LOCAL_LLM_MCP.md) |
| Diagnose an error | [Troubleshooting](../TROUBLESHOOTING.md) · [Error codes](ERROR_CODE_CATALOG.md) |
| Use the command line | [CLI workflow](CLI_WORKFLOW.md) · [CLI reference](CLI.md) |

## Develop SPIKE

- [HyperLynx parity and multiphysics plan](HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md): capability gaps, qualification milestones and cross-domain workflows.
- [Development setup](../DEVELOPMENT.md) and [architecture](../ARCHITECTURE.md)
- [Subsystem index](SUBSYSTEM_INDEX.md), [contracts](CONTRACTS.md), and [developer guide](DEVELOPER_GUIDE.md)
- [Solver handbook](SOLVER_HANDBOOK.md) and [references](SOLVER_REFERENCES.md)
- [Security model](SECURITY_MODEL.md) and [contributing](../CONTRIBUTING.md)

Optional external engines are separate installations. Their availability is
shown in SPIKE before an analysis runs.

[MCP and SpiDeR interfaces](MCP_SPIDER_INTERFACES.md): modern/legacy discovery,
offline schema resources, canonical design inspection and revision evidence.
