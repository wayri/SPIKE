# Interactive analysis guide

Open **Help → Interactive analysis guide** to show a floating guide over the
SPIKE workspace. Choose HF / SI EMerge S-parameters or radiation, or one of the internal
SPIKE paths: copper DC/PI, PEEC AC/transient, SI channel, EMI screening, object
thermal, board thermal, or native circuit MNA.
Each workflow has a short sequence for importing a board, setting up an
analysis, locating its Run control, and reviewing the result.

**Next** and **Back** move between steps. **Find control** scrolls to and
focuses the current control. A pulsing outline marks it; the guide reports
when that control is unavailable. You can move the floating window by its
heading and close it at any time. The guide never chooses engineering inputs
or starts an analysis on your behalf.

Each workflow displays its capability and validation boundary. The
**Recommended next step** section at the bottom responds to whether a board is
loaded, a control is available, and a result exists. It links to the next guide
step and suggests a workflow-specific result check at the end. The internal
PEEC, SI, thermal, and circuit paths retain their experimental or approximate
status; full-wave 3D and arbitrary-board S-parameters are not presented as
validated built-in capabilities.

For EMerge SI, the guide opens **HF / SI**, highlights the **S-parameter
solver** selector, and directs you to **Check EMerge** if the choice is not
available. **SPIKE internal** remains the default. The EMerge choice becomes
available only after a trusted EMerge extension runtime probe reports
`si_s_parameters`; it changes only the **S-parameters** and **Ports** commands.
The guide then points to the EMerge net/port, sweep, mesh, Run, and result
controls. EMerge radiation opens **EM → EMerge**. Runtime availability is not
solver readiness, and EMerge S-parameter results remain `unvalidated`. Results
retain their model status, warnings, and provenance. See the
[EMerge antenna walkthrough](EMERGE_ANTENNA_WALKTHROUGH.md) for a concrete
two-layer setup and interpretation of its 3D pattern and S-parameter plots.

The guide's navigation and highlighting are UI help only. It does not change
the solver capability or validity rules in [Solver status](SOLVER_STATUS.md).
