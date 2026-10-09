# SPIKE documentation

<img src="../app/public/spike-logo.png" alt="SPIKE logo" width="420">

Start with the guides that match what you want to do. [Solver status](SOLVER_STATUS.md)
describes which analyses are available and what their results mean.

## Use SPIKE

| Task | Guide |
| --- | --- |
| Try SPIKE in five minutes | [ESP32 quickstart](ESP32_QUICKSTART.md) |
| Import a board and explore the desktop | [User tasks](USER_TASK_SEQUENCES.md) · [Result visualization](RESULT_VISUALIZATION_AND_LIMITS.md) |
| Run power analysis | [PI paths](PI_PATH_ANALYSIS.md) · [DC solver](DC_SOLVER.md) · [Transient PI](TRANSIENT_PI.md) |
| Run signal analysis | [SI user guide](SI_USER_GUIDE.md) · [SI workflow](SI_WORKFLOW.md) |
| Explore board temperature | [Thermal user guide](THERMAL_USER_GUIDE.md) · [Thermal workflow](THERMAL_WORKFLOW.md) |
| Explore antenna and EM results | [EM workflow](EMI_WORKFLOW.md) · [EMerge example](VIRTUAL_EMI_EMERGE_TUTORIAL.md) |
| Mesh a complete planar PCB with local refinement | [Focused volume meshes](PCB_FOCUSED_VOLUME_MESHING.md) |
| Work through examples | [Tutorial atlas](CAPABILITY_TUTORIAL_ATLAS.md) · [ESP32 example](../examples/esp32/README.md) |
| Connect a local language model | [Local LLM and MCP](LOCAL_LLM_MCP.md) |
| Diagnose an error | [Troubleshooting](../TROUBLESHOOTING.md) · [Error codes](ERROR_CODE_CATALOG.md) |
| Use the command line | [CLI workflow](CLI_WORKFLOW.md) · [CLI reference](CLI.md) |

## Develop SPIKE

- [Development setup](../DEVELOPMENT.md) and [architecture](../ARCHITECTURE.md)
- [Subsystem index](SUBSYSTEM_INDEX.md), [contracts](CONTRACTS.md), and [developer guide](DEVELOPER_GUIDE.md)
- [Solver handbook](SOLVER_HANDBOOK.md) and [references](SOLVER_REFERENCES.md)
- [Security model](SECURITY_MODEL.md) and [contributing](../CONTRIBUTING.md)

Optional external engines are separate installations. Their availability is
shown in SPIKE before an analysis runs.
