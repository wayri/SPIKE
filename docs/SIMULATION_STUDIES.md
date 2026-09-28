# Simulation studies

Open **File → Simulation studies** or **Project manager → Simulation studies**.
A study is an ordered collection of cases. PI, SI, thermal, and EM cases may
appear in any order, and a type may appear more than once. Give repeated cases
distinct condition labels, such as *open air* and *closed box*.

1. Create a study, name it, and add cases with **Add simulation**.
2. Activate a case to load its saved settings into its analysis workspace.
   A case recorded for a different board file will not activate.
3. Review or change the setup and run it using that workspace's normal solver
   controls. A study does not bypass preflight or run every case automatically.
4. Return to Simulation studies. Choose **Save current setup** if inputs
   changed, then **Capture result** after the simulation returns a result.
5. Save the `.spike` project to retain the cases and their captured results.

Cases can be renamed, annotated, reordered, duplicated, or removed. Duplicating
a case copies its setup and clears its result. Changing a case's type, mode,
scenario, or saved setup also clears its previous captured result to avoid
presenting stale data as current. The **Save project copy without results**
action retains study definitions and setups while omitting captured results.

The study manager organizes existing analyses. Solver capability and numerical
qualification remain as documented in [SOLVER_STATUS.md](SOLVER_STATUS.md).
