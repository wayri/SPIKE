<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE 0.3.9 demonstration guide

These are reproducible experimental studies, not validated hardware designs.
The numerical requests and results are recorded separately from the `.spike`
projects. Interactive Windows walkthrough acceptance remains pending because
the verification desktop was locked. Control names below match the implemented
UI; they are not a claim that every click was recorded successfully.

## Multiboard PI, SI and thermal

Local examples:

| Assembly | Project | Evidence |
| --- | --- | --- |
| Arduino UNO R4 Minima + four-relay shield | `build/curated-multiboard-20261005/arduino/arduino-r4-relay-shield.spike` | Same directory: domain requests/results, placement, provenance and worker verification |
| Raspberry Pi CM4 IO + Sailor Hat | `build/curated-release-20261009-v2/raspberry-pi/cm4io-sailor-hat.spike` | Same directory: acceptance, placement, source provenance and frozen source verification |

The Raspberry Pi package is local-use-only: the supplied CM4 archive contains
no explicit redistribution grant. It must not be uploaded with the public
release. The Sailor Hat source retains its pinned revision and CC BY 4.0
attribution. Inspect each example's provenance before sharing source assets.

1. Open the project using **File > Open**. Review both board occurrences,
   placements and explicit connector links. Equal net names alone do not
   connect different board designs.
2. Open **Results > Fields**, then **Saved assembly results**.
3. Select **Show PI result**. This validates its saved request and assembly
   identity, then displays numerical tables without browsing another file.
4. Select **Show SI result** and **Show Thermal result** similarly. Review
   model status, warnings and assumptions alongside the numbers.
5. For a rerun, open the assembly workspace and its study editor. Keep the
   recorded explicit network parameters and thermal conditions. Save edits
   before running; compare with the directory's domain result JSON.

These examples use reduced networks and declared loads. They do not infer a
full-wave PCB/harness radiation problem from artwork or establish EMI compliance.
Changing source, placement, connections or setup invalidates retained results.

## Transient solid thermal: two boards and a STEP part

Fresh candidate artifacts:

- Project: `build/preview-0.3.9/thermal-study/original-transient.spike`.
- Complete geometry, boundary/load problem and time settings: `geometry.json`,
  `problem.json`, `settings.json` in that directory.
- Actual internal and CalculiX histories: `spike.json`, `calculix.json`.
- Comparison and reopened-package admission: `comparison.json`, `reopen.json`.
- Extracted frozen-worker admission: `build/preview-0.3.9/final-thermal-reopen.json`.
- GIF, final PNG and encoding provenance:
  `build/preview-0.3.9/demonstrations`.

1. Open this benchmark project, then the assembly workspace's **Assembly volume
   field study**. Its retained result loads from the package; **Open volume
   study** is for a separate study file, not required for an embedded study.
2. Inspect physical materials, heat capacities, boundary conditions, contacts
   and time settings. Select **Transient solid thermal** when editing a new
   study. This benchmark is an original synthetic geometry, not a real PCB's
   validated material characterization.
3. Use the thermal volume viewer's saved-frame play, pause, seek and speed
   controls. They follow returned simulation timestamps.
4. To run again, select **SPIKE reference tetrahedral solver** or the separately
   installed **CalculiX** runtime and choose **Run transient thermal**. Live
   frames are provisional; **Cancel thermal run** cancels execution. Playback
   pause does not pause the numerical job.
5. Review energy balance and model limitations before saving or exporting.
   Native viewport GIF/WebM codec acceptance remains a release check.

The fresh comparison covers 288 nodes and five retained times. Maximum absolute
SPIKE/CalculiX difference is 0.011425845 K under the declared 0.05 K plus 5%
local-temperature-change allowance. Cross-engine agreement is not measured
physical accuracy. The GIF uses these exact samples at 0.1x speed and a final
1.5-second hold. Surface colors are triangle means of nodal temperatures.

To reproduce the original benchmark with the declared external runtimes, see
the [thermal validation procedure](../validation/ASSEMBLY_THERMAL_TRANSIENT_20261008.md).
To render an admitted history without rerunning a solver:

```powershell
.venv/Scripts/python.exe scripts/render_transient_thermal_demo.py build/preview-0.3.9/thermal-study build/preview-0.3.9/demonstrations
```

## Behavioral closed-loop PWM electrothermal reference

1. Open **PI** or **Thermal** and locate the PWM electrothermal reference panel.
2. Inspect source voltage, buck L/C/load, switch conductances, winding resistance,
   thermal resistance/capacity, controller gains and timestep/cycle count.
3. Validate the exact request, then run. The default 400-cycle case covers 20 ms.
4. Inspect cycle voltage/current envelopes, duty, winding temperature, energy
   accounting and numerical dissipation. A default native run ended at
   4.9706687 V and 300.52797 K; those values apply only to its recorded parameters.
5. Save the project to retain the request-bound result. Changing parameters
   prevents stale output from being presented as the new setup's result.

This is a bounded MNA buck and cycle PI-control reference. It does not qualify
vendor MOSFET losses, deadtime, device thermal cooling, spatial PCB electrothermal
feedback, airflow, arbitrary Verilog models or radiated EMI. See the
[capability audit](../CAPABILITY_ACCEPTANCE_20261009.md) for remaining work.
