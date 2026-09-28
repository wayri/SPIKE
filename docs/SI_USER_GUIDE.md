<!-- SPDX-License-Identifier: Apache-2.0 -->

# Signal integrity in SPIKE: board context and a reproducible four-port study

This tutorial starts with the open-source [Marble v1.4.4 board](https://github.com/BerkeleyLab/Marble) as physical design context, then runs the complete **implemented** SI workflow on an independently authored analytical coupled line. The two inputs must not be confused: the plots below are **not Marble S-parameters or Marble eye measurements**. Current board extraction and full-wave admission do not support a validated four-port Marble channel. The [SI capability record](validation/SI_CAPABILITY_VOLUME_PEEC_20260928.md) and [solver status](SOLVER_STATUS.md) record the evidence and remaining gates.

## 1. Get the board and inspect the physical path

The local evaluation used Marble v1.4.4, commit `a426777d92c0f22a546d4740b419a3937e0c1f90`, with its KiCad PCB at `design/Marble.kicad_pcb`. That repository is CERN OHL v1.2; its source and license remain with the board author. See the [source record](CERN_MARBLE_EVALUATION_20260920.md). Download a release/source tree from the Marble project if it is not already present; the board file is deliberately outside SPIKE source control.

1. Start the native desktop using [Development setup](../DEVELOPMENT.md). From this repository, `Set-Location app; npm.cmd run tauri dev` is the Windows development command. A packaged desktop can be launched directly.
2. Choose **Home -> Import** and select `design/Marble.kicad_pcb`; save the `.spike` project. Check **Home -> Issues / Import Quality** before interpreting geometry.
3. In the 2D copper view, select the target layer and signal net, zoom to both intended endpoints, and inspect the object net and coordinates. Enable **View -> Show net names**. Record a distinct return conductor, material stackup, launch locations, source/receiver reference planes, and port impedance from actual design or fabrication data.
4. Use the board image below to orient the UI. It is an import capture, not a solver result.

![Imported Marble board in SPIKE](tutorial-assets/pi-si-openems/marble-workspace-3d.png)

*Marble v1.4.4 import capture from SPIKE 0.2.12. Copper display and procedural component bodies help locate geometry; no electrical response is established by this image.*

Marble's local `+1V0` PEEC experiment yielded an **approximate driving-point** response on a provisional copper slice. At 100 MHz it returned `0.0188 + j0.4072 ohm`; at 1 GHz, `0.1110 + j4.0034 ohm`. It is a power-net slice and cannot be treated as a signal-channel S matrix, a 50 ohm interconnect, or an eye. Its volume model and limits are in the [SI capability record](validation/SI_CAPABILITY_VOLUME_PEEC_20260928.md). Full-board openEMS admission is blocked by selected pad/via topology, and a multiport excitation/port-calibration study has not been performed; see the [board comparison](validation/OPENEMS_BOARD_COMPARISON_20260927.md).

## 2. Run the four-port reference channel

The checked-in [analytical request](../examples/si/analytical-coupled-rlgc.json) describes a 5 cm coupled RLGC line, 50 ohm reference, 0-8 GHz uniform sweep with 1,025 points, one source and one receiver, and a 1 Gb/s NRZ record. Its resistance, inductance, capacitance, loss and coupling numbers are explicit modeling assumptions, not values extracted from Marble. JSON port indices are zero-based.

From the repository root, in a Python environment with the documented dependencies, run:

```powershell
python -m python.spike_core.cli --output build/si-guide-result.json si-workflow examples/si/analytical-coupled-rlgc.json --touchstone-output build/si-guide-channel.s4p
```

The equivalent direct Python entry point is useful when only the SI package dependencies are installed:

```powershell
python -c "import json; from pathlib import Path; from python.spike_core.si_workflow import run_si_workflow; request=json.loads(Path('examples/si/analytical-coupled-rlgc.json').read_text()); result=run_si_workflow(request); Path('build/si-guide-result.json').write_text(json.dumps(result, indent=2, allow_nan=False)); print(result['status'], result['time_domain']['status'])"
```

The first command also exports the **edited, unloaded channel** as Touchstone. Endpoint source/receiver impedances, passive loading, and the receiver eye are reported in JSON, not embedded in that `.s4p` file. If CLI startup reports a missing Python package, install this repository's [development prerequisites](../DEVELOPMENT.md) in the interpreter used for the command; do not interpret an import failure as a solver result.

For the desktop path, open **HF / SI -> S-parameter workbench -> Source-to-receiver workflow**. Enter the request's channel, endpoint and clock values or import the saved setup JSON. In the source-to-receiver tab, run with the native desktop worker. A browser preview can configure and display saved results but cannot execute this worker. Save the setup and resulting JSON or the `.spike` project; edits after a run make its prior result stale.

The reference run completed `frequency`, `time_domain`, and `tdr` stages with `model_status: experimental`, four ports, and receiver eye height `1.765625 V`. The same numbers were checked by executing the checked-in request. The [existing plotted evidence](validation/SI_CAPABILITY_VOLUME_PEEC_20260928.md) was generated by `scripts/plot_si_capability_evidence.py` from the same default coupled-line parameters.

![Analytical coupled line: through, NEXT, FEXT, VSWR, eye, and TDR](tutorial-assets/pi-si-openems/analytical-si-workflow.png)

*Executed analytical coupled-RLGC reference. This image is a network-model result; it contains no board extraction or measured hardware correlation.*

## 3. Read each SI result

The default coupled-line ordering is **port 1 aggressor near, 2 victim near, 3 aggressor far, 4 victim far**. Thus with port 1 excited, `S31` is aggressor through transmission, `S21` is near-end crosstalk (**NEXT**), and `S41` is far-end crosstalk (**FEXT**). The traces report complex S-parameter magnitude and phase against frequency. Imported Touchstone files require their own verified port map; port numbering alone does not assign a physical aggressor, victim or return path.

| View | What to check | Interpretation boundary |
| --- | --- | --- |
| S magnitude/phase | `S11` return and `S31` through, with `S21`/`S41` coupling | Matched-reference linear network data; no connector or PCB correlation follows from an analytical line. |
| Reflection and VSWR | Per-port `Sii` and status of each VSWR sample | `VSWR = (1 + |Gamma|)/(1 - |Gamma|)` for passive finite `|Gamma| < 1`. Unit reflection is infinite; `|Gamma| > 1` is marked non-passive and has no passive VSWR. Gaps are deliberate. |
| Input impedance | Port-1 driving point with other ports terminated at real reference resistances | It differs from a loaded receiver die impedance and from PEEC's provisional board driving point. |
| TDR/TDT | Returned time-domain reflection, impedance and transmission | Uses the sampled channel sweep. Check time resolution and processing limits before locating a discontinuity. |
| Loaded transfer and waveform | Source-to-receiver die voltage and threshold crossings | The source level is open-circuit Thevenin voltage. Source/load division and package/receiver C affect the result. |
| Eye | Eye height, high/low margins, cursor phase and waveform traces | Deterministic finite PRBS7 response at the stated rate; no stochastic BER, jitter mask or protocol compliance. |
| Noise | Passive thermal/excess noise and separate receiver input noise | Noise is **not injected into the plotted deterministic eye**. Channel-loss/internal receiver noise transfer is incomplete. |

Open **NEXT / FEXT** in the geometry channel tab only with a **separate explicit victim net**, reference net and copper layer. The geometry channel's bounded result is source-to-victim-near/far transfer; a visually adjacent net is not automatically a calibrated coupled pair. **Eye diagram** and **PAM4** select runnable geometry channel settings. **Ports** opens source/receiver assignments in the loaded workflow. The [workflow reference](SI_WORKFLOW.md) describes both tabs and the detailed request model.

To compare terminations, change only one explicit assumption at a time, rerun, and compare S traces with loaded transfer and eye. Adding a receiver capacitance or a shunt/series passive changes the loaded result; the unloaded Touchstone channel export remains a separate object. Optional network edits include renormalization, port reorder, electrical delay and a same-grid two-port cascade. The UI uses one-based ports, whereas JSON uses zero-based ports; verify assignments after reordering. IBIS import inventories pins/models and permits an explicit DC-slope/ramp small-signal reduction. It does not run nonlinear IBIS switching or IBIS-AMI.

## 4. Diagnose partial and unsupported outputs

Read the result's `status`, `model_status`, `warnings`, `limitations`, `network.issues`, `time_domain.status`, `tdr.status`, `field_maps.status`, request digest, and port map before using a graph. A blocked requested time stage can leave valid frequency-domain results with overall `status: partial` and a nonzero CLI exit. For an eye or TDR, the sweep must include DC and uniform spacing, have sufficient bandwidth for at least eight samples per unit interval, and represent the requested rate within 1%. Increase bandwidth/point count or adjust the bit rate and rerun; SPIKE does not silently extrapolate DC or repair causality. Finite PAM4 records need at least 64 supported symbols after delay trimming.

The network result reports `field_maps: unsupported`. A field viewer can plot E/H only if a selected `AnalysisResult` actually supplies finite three-component spatial vectors. Neither S-parameters, TDR nor the Marble PEEC driving-point response can be turned into a physical E/H map by the viewer. The optional openEMS Suite can preflight a board and run admitted field cases, but current Marble and White Rabbit whole-board topology/material/port gates prevent a qualified board S matrix; see the [openEMS tutorial](PI_SI_OPENEMS_TUTORIAL.md#6-run-an-openems-suite-preflight-then-a-bounded-case).

For board-level claims, obtain verified copper/fill topology, physical stackup and return path, reviewed calibrated ports, a full N-excitation matrix, mesh and time convergence, passivity/reciprocity checks, and independent measurement or trusted reference correlation. The current analytical example establishes tool behavior and plot interpretation only. `production_qualified` remains false and `compliance_status` is `not_evaluated`.
