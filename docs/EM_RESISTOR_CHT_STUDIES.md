<!-- SPDX-License-Identifier: Apache-2.0 -->
# Saved AC resistor and CHT studies

The experimental AC resistor-to-CHT runner can export an existing version-one
SimulationStudy document containing the complete reviewed request, its bound
result and historical captures. This is a source application workflow;
installed application acceptance remains a separate gate.

## Prepare and save

Open the **Run AC resistor / solid / fluid heat coupling** Python template.
Set `REQUEST_FILE` to a worker-parameter JSON object containing exactly one
`request` field. Set `STUDY_FILE` to a new JSON output path. Run the reviewed
script, import its exported document in Simulation studies, then save the
project to retain it in `.spike`. Result-only export remains available through
`RESULT_FILE`. Existing output files are refused.

To continue a saved investigation, use `STUDY_INPUT` for the exported study,
or activate its imported case to stage a runner with that case embedded.
Activation validates the saved request and stages editable code; it does not
run the solver or publish an old result into the current field workspace.
Use `REQUEST_FILE` alongside an embedded study to replace its physical inputs
while retaining history. Choose a new `STUDY_FILE` for the updated export.
Importing that export uses the existing copy-on-import behavior; it creates
a separate investigation rather than silently overwriting another study.

Only one case is selected for a staged runner. A standalone input with multiple
cases is rejected as ambiguous. Material, retained geometry, boundary conditions,
ordered port names, source data and explicit solid-cell heat allocations stay
inside the complete request. No geometric or thermal contact inference is added.

## Identity and invalidation

`em_resistor_cht_study.py` owns application-level admission and currentness.
The worker method `prepare_em_resistor_cht_study` takes the existing
`{request: payload}` envelope; payload contains `request` and optional `study`
and `result`. It returns a SimulationStudy with case type `em-resistor-cht`,
mode `steady` and the physical request under `settings.request`.

Before staging or solving, preparation checks retained mesh admission, declared
material phases, explicit port destinations, zero pre-existing volume sources
and a selected frequency. The unchanged numerical runner still owns complete
AC/CHT boundary, equation and numerical admission. Preparation is not a solve
or a physical qualification.

A current result must report the expected parent and child contracts,
experimental status, `production_qualified=false`, completed CHT fields and
diagnostics, plus canonical input and mesh digests matching the request.
Digests bind supplied data; they do not authenticate its author or independently
validate the physics. A corrupt current snapshot on unchanged inputs is rejected.

Changing power excitation, conductivity, boundary temperatures or geometry
clears the current result and any external result reference, retaining old runs
with their original requests. An unchanged canonical setup save or presentation
rename preserves its result. New captures have actual UTC capture times and
distinct identities; reopening does not create another capture. Historical
captures remain explicitly labeled and do not become a fresh solve by activation.

The ordinary project snapshot merger treats study settings/scenarios as complete
authoritative objects. Removed physical keys and invalidated results cannot
be resurrected from an older retained snapshot. Other future project fields
continue to use the existing preservation behavior.

## Bounds and verification

The service retains the existing 8 MiB worker request envelope limit. This
specialized study has a 3 MiB complete-document limit, enforced by preparation
and study import, so a study plus its request can traverse that envelope again.
The script uses the same 3 MiB file budget and compact UTF-8 JSON output.
The helper also bounds individual results at 16 MiB and history at 100 runs;
the complete-study limit applies first. Other study types keep their existing
generic limits. These are admission limits, not peak resident memory claims.

Embedded editor drafts have the existing 512 KiB code limit. Larger admitted
studies remain runnable through the small template with `STUDY_INPUT`; activation
reports that path rather than staging an oversized draft.

Focused checks:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_em_resistor_cht_study tests.python.test_em_network_resistor_cht tests.python.test_em_network_cht_release_route -v
cd app
npm.cmd run test:studies
npm.cmd run test:study-result-activation
npm.cmd run test:study-navigator
npm.cmd run test:python-workspace
npm.cmd run test:project-persistence
```

The cross-language study test executes the real worker service and solver through
the generated runner, round-trips its request/result, checks all four physical
edits and retained history, and reruns the embedded case. Python tests also
write/read an actual `.spike` package. App-handler tests exercise rejection,
staging without numerical execution, and late-response project switching.
These checks do not establish native GUI visual or installed lifecycle acceptance.

See [the numerical scope and analytical reference](validation/AC_NETWORK_CHT_20261023.md)
and [generic simulation study behavior](SIMULATION_STUDIES.md).
