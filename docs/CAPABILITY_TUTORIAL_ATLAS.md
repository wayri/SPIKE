<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright (c) 2026 SigHarmonic -->

# SPIKE capability tutorial atlas

This is the entry point for the **currently executable** PI, SI, thermal and
two bundled solver-extension families. Each linked lab identifies inputs,
commands or desktop controls, returned JSON/plots and interpretation limits.
The linked images are executed results or clearly labelled interface captures;
an image alone never qualifies a physical prediction. Start with
[development setup](../DEVELOPMENT.md), [current solver status](SOLVER_STATUS.md)
and the [result-state vocabulary](RESULT_VISUALIZATION_AND_LIMITS.md).

Use a native desktop for worker-backed UI studies. Browser preview shows
controls and saved artifacts but cannot execute the local worker. Save the
board revision, stackup, material/source assumptions, port map and result
provenance with each study. If an input or solver is unavailable, use the
analytical fixture rather than silently substituting a fabricated board claim.

## Power integrity

| Exercise and exact input | Run and inspect | Example output / image | Status boundary |
| --- | --- | --- | --- |
| Routed copper DC, source/load terminals, voltage drop and current density on an [original straight trace](../examples/tutorial_pi_si/straight_trace.design.json) | [Casebook §1](PI_SI_WORKED_CASEBOOK.md#1-routed-copper-dc-pi); [desktop PI task](PI_SI_OPENEMS_TUTORIAL.md#2-internal-dc-pi-voltage-drop-and-current-flow) | `build/tutorial-pi-si/dc-result.json`; [DC capture](tutorial-assets/pi-si-casebook/dc.png) | Analytical geometry fixture, not board sign-off; repeat mesh sizes. |
| AC/broadband PEEC driving-point R/L and energy rejection | [Casebook §2](PI_SI_WORKED_CASEBOOK.md#2-acbroadband-pi-driving-point-impedance); [Marble rejection §7](PI_SI_WORKED_CASEBOOK.md#7-marble-ac-is-a-rejection-tutorial) | `ac-result.json`; [AC capture](tutorial-assets/pi-si-casebook/ac.png); [rejected Marble capture](tutorial-assets/pi-si-casebook/marble-gate.png) | Approximate impedance, not qualified C/G or multiport S parameters; a rejected mesh is not a result. |
| PI current step, branch losses and temporal frames | [Casebook §3](PI_SI_WORKED_CASEBOOK.md#3-geometry-derived-pi-transient) | `transient-result.json`; [transient capture](tutorial-assets/pi-si-casebook/transient.png) | Experimental, check time-step convergence and source history. |
| Connector/harness source, sink and mated contacts | [Harness PI guide](HARNESS_PI.md) | `harness-pi` JSON result | Lumped DC harness model, not PCB-field or connector SI coupling. |
| Thermal consequence of DC resistor loss | [Structured electrothermal example](../examples/thermal/README.md) | `build/structured-electrothermal-result.json` | Closed-loop reference resistor only; not switching-device power integrity. |

## Signal integrity and SERDES

| Exercise and exact input | Run and inspect | Example output / image | Status boundary |
| --- | --- | --- | --- |
| RLGC/Touchstone, ports, loaded transfer, S-parameters, impedance, VSWR, TDR and eye | [SI user guide](SI_USER_GUIDE.md); [worked casebook §§4–5](PI_SI_WORKED_CASEBOOK.md#4-si-channel-crosstalk-tdr-and-eye) | `si-result.json`, exported `.s4p`; [SI capture](tutorial-assets/pi-si-casebook/si.png), [Touchstone capture](tutorial-assets/pi-si-casebook/touchstone.png) | Analytical/imported network; no spatial E/H field inferred. |
| Four-port NEXT/FEXT and coupled-line eye on [analytic fixture](../examples/si/analytical-coupled-rlgc.json) | [Casebook §4](PI_SI_WORKED_CASEBOOK.md#4-si-channel-crosstalk-tdr-and-eye), [port ordering](SI_WORKFLOW.md) | `si-result.json`; [waveform/TDR capture](tutorial-assets/pi-si-casebook/si-time.png) | Experimental crosstalk, not board-pair correlation. |
| Real pad/net topology, mid-path resistor, illustrative IBIS and Touchstone | [Marble R293 guided lab on the reviewed integration branch](https://github.com/wayri/SPIKE-Main/blob/codex/pi-si-guided-casebook-20260928/docs/MARBLE_R293_SI_TUTORIAL.md) | Reproducible `impact-report.json` and the branch's executed capture | Not yet merged into this checkout; real connectivity but synthetic channel/device models, no Marble margin. |
| NRZ/CDR at a 10.3125-GBd *numerical* reference rate | [Casebook §6](PI_SI_WORKED_CASEBOOK.md#6-103125-gbd-nrzcdr-numerical-reference) | `10g-reference-result.json`; [10G capture](tutorial-assets/pi-si-casebook/10g.png) | Not 10GbE PHY or protocol compliance. PAM4/BER approximations and limitations are in [SI workflow](SI_WORKFLOW.md). |
| Explicit source/receiver/passive/IBIS reduction, port reorder/delay/cascade and renormalization | [SI workflow reference](SI_WORKFLOW.md), [reviewed Touchstone/IBIS lab](https://github.com/wayri/SPIKE-Main/blob/codex/pi-si-guided-casebook-20260928/docs/MARBLE_R293_SI_TUTORIAL.md) | Loaded transfer, eye/TDR and declared validation state | Branch lab is pending integration; fixture de-embedding, nonlinear IBIS and AMI are not implemented by this path. |

## Thermal and electrothermal

| Exercise and exact input | Run and inspect | Example output / image | Status boundary |
| --- | --- | --- | --- |
| Component/object steady and transient thermal RC | [eBrake1 object example](../docs/validation/EBRAKE1_OBJECT_THERMAL_20260928.md); [thermal user guide](THERMAL_USER_GUIDE.md) | Saved result JSON, [object plot](validation/ebrake1-object-thermal.png) | Lumped temperatures, not spatial PCB field. |
| Marble board uniform plate and eBrake1 board gradient | [Thermal guide §§3–4](THERMAL_USER_GUIDE.md#3-open-source-exercise-marble-uniform-board-plate); [board example](../examples/thermal/README.md) | [Marble plate](validation/marble-v144-plate-thermal.png), [eBrake1 board](validation/ebrake1-board-thermal.png) | Bounding-rectangle effective material, hypothetical heat loads. |
| eBrake1 layered copper/pad/via path and virtual sink | [Layered guide](THERMAL_USER_GUIDE.md#4-layered-exercise-bundled-ebrake1-fixture), [virtual sink section](THERMAL_USER_GUIDE.md#optional-mathematical-heatsink-on-the-layered-board) | [Layer map](validation/ebrake1-layered-thermal-exact.png), [sink figure](validation/ebrake1-layered-virtual-heatsink.png) | One depth cell per stackup row; sink is a mathematical boundary, not fin CFD. |
| eBrake1 layered transient and sensitivity | [Thermal guide §6](THERMAL_USER_GUIDE.md#6-animate-the-layered-board-and-inspect-transient-analytics) | [Final frame](validation/ebrake1-layered-transient-final.png), [animation](validation/ebrake1-layered-transient.gif) | Approximate cell heat capacity and constant-power stepping. |
| Bounded 3-D solid conduction, DC electrothermal and pulsed diode | [Three executable requests](../examples/thermal/README.md) | `build/structured-*-result.json` | Development references with `production_qualified:false`; no general semiconductor or enclosure airflow. |
| OpenFOAM enclosure/airflow preparation | [Thermal workflow](THERMAL_WORKFLOW.md) | Prepared case/readiness or imported result when separately available | Optional external solver, not implied by a plate/layered run. |

## The two bundled solver extensions and virtual EMI

| Extension / exercise | Run and inspect | Example output / image | Boundary |
| --- | --- | --- | --- |
| **OpenEMS Suite**: HF PI and SI preflight, prepared case, single-excitation field run where admitted | [OpenEMS tutorial §§5–7](PI_SI_OPENEMS_TUTORIAL.md#5-install-and-discover-the-optional-openems-runtime); [extension README](../extensions/openems_suite/README.md) | Case manifest, imported S parameters and [two-port interface capture](tutorial-assets/pi-si-openems/openems-two-port.png) | Runtime optional; arbitrary PCB convergence/correlation not established. This package does not contribute an EM-tab button. |
| **EMerge Suite**: bounded two-layer SI port sweep and relative radiation | [Antenna walkthrough](EMERGE_ANTENNA_WALKTHROUGH.md); [radome comparison](../examples/emerge/radome/README.md) | [S11/cut](../examples/emerge/antenna_plots.png), [3-D pattern](../examples/emerge/antenna_pattern_3d.png) | Unvalidated selected-net surface-PEC model; relative pattern is not an emissions level. |
| **EM tab + EMerge**: net screening, runtime radiation result and virtual chamber overlay | [Guided virtual EMI lab](VIRTUAL_EMI_EMERGE_TUTORIAL.md) | `build/tutorial-virtual-emi/virtual-emi-review.json`; [executed capture](tutorial-assets/virtual-emi-emerge.png) | EMI screen and EMerge solve are separate. Chamber pose/absorbers are visual; field scan uses openEMS, not EMerge. No compliance verdict. |

The project also contains non-solver extensions (for example inventory,
conversion and MCAD). “Two extensions” here means the two bundled **solver**
extensions, not the complete extension catalog. A missing example, screenshot,
runtime dependency or validated physical claim must stay visibly pending; see
[solver status](SOLVER_STATUS.md) and [release gates](PUBLIC_RELEASE_READINESS.md).

## Explicitly pending, so not presented as completed tutorials

- PI sign-off on arbitrary copper/zone/port topology and a qualified full
  broadband multiport RLCG matrix still require convergence, energy,
  reciprocity, passivity and independent/measured comparison.
- General nonlinear IBIS/AMI, fixture de-embedding, causal macromodel
  enforcement and Ethernet compliance are not established by the loaded SI
  tutorial or its numerical 10G reference.
- Arbitrary enclosure airflow, detailed semiconductor power-loss coupling,
  calibrated package/board temperatures and measured thermal correlation are
  not implied by the plate, layered or reference-solid examples.
- The virtual chamber's appearance and EMerge relative pattern cannot be
  converted into dBµV/m at a regulatory receiver without a validated
  absolute-power chain, antenna/detector model and measurement correlation.
