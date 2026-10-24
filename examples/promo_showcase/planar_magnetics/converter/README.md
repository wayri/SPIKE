# 48 V → 1.8 V / 50 W planar-converter study

This is a complete editable **topology and routed geometry study**, plus an executed native Studio ideal-converter example. It is **not a fabrication-ready or current-qualified 50 W converter**. Power semiconductors, gate drivers, protection, insulation, component ratings, copper temperature rise and connector sharing remain unqualified. No hardware energization or release is authorized by the supplied files.

## Native files

- Open `carrier.kicad_pro` in KiCad 10.0.6; matching schematic and board plus local `Carrier.kicad_sym`, `Carrier.pretty`, symbol/footprint tables are included.
- The native schematic contains the full four-MOS primary bridge, 34-pin transformer module, four-MOS synchronous secondary bridge, output L/C, input/output and external G/S driver connectors. All MOS symbols and footprints are explicitly generic placeholders.
- Board: 100 × 90 mm, module origin (50,45) mm, 32.5 × 21.1 mm internal cutout for the protruding lower core, documentary 52 × 52 mm component-envelope border. The component border is not an enforced clearance/insulation rule.
- Every one of the 81 native required pad connections was routed across the two copper layers. All traces are 0.5 mm wide **geometric examples, not rated for the 27.8 A load**. Native DRC, unconnected count and schematic parity are each zero. No finding was excluded to achieve that result. Native reports retain the installed KiCad default ignored-check list.
- T1 local model is `${KIPRJMOD}/models/planar_transformer_assembly.step`. It contains the original 225-solid full module with two core halves, actual winding-board bodies/copper and 34 original pin solids; stock third-party header models are omitted. Native KiCad STEP export of the carrier with this model contains 226 manifold solid records (225 model solids + carrier body). Other carrier parts do not have 3D models and are not silently replaced with invented detailed packages.

T1 pin contract, relative to module origin in PCB mm:

| Terminals | Pads and positions | Net / polarity |
| --- | --- | --- |
| Primary | 1 at (-20,-1.27), 2 at (-20,+1.27) | PRI_A / PRI_B; dot P1 |
| Secondary S1 | 3..18: eight x positions -8.89,-6.35,-3.81,-1.27,+1.27,+3.81,+6.35,+8.89; rows y=20,22.54 | SEC_A; undotted |
| Secondary S2 | 19..34: same x positions, rows y=-20,-22.54 | SEC_B; dotted |

Primary P1 positive corresponds to secondary S2 positive under the companion winding orientation. The schematic dots and simulation `sec_b`/`sec_a` mapping preserve that sign. Symmetric rectification does not make the sign convention optional for other uses. Berg/header pin geometry is not a rating: 16 parallel contacts per secondary bank do not establish balanced sharing or safe total current. J3/J4 are original 5.08 mm external-driver G/S test-pad grids, not sourced Berg connector footprints.

## Run the native Studio example

In SPIKE Studio, **File > Open `converter.spksch`**; choose the owned native engine `app/src-tauri/resources/worker/spike-worker/_internal/spikes/spikes_c_api.dll` from this repository. The sibling circuit-worker DLL lacks the needed dependent-source ABI in this installation. The project retains graphical routes, voltage/current probes, three scopes and a **backward Euler** run profile. Run transient, inspect V(out), I(Lout), V(pri), and switch to Dashboard Run mode for the recorded scopes. No UI execution or recording is claimed by this package task.

Reproduce from repository root:

```powershell
.venv/Scripts/python.exe examples/promo_showcase/planar_magnetics/converter/run_converter.py
```

Matching `converter-base.cir` and `converter-refined.cir` are supported native netlists. Raw actual results and checks are under `output/promo-planar-magnetics-20261023/converter/`. The saved Studio project uses the refined 50 ns request and was reopened/source-checked through the native document API.

| Executed step | Mean output | Mean load current | Load power | Output ripple peak-to-peak |
| --- | --- | --- | --- | --- |
| 100 ns | 1.799921 V | 27.77655 A | 49.99564 W | 6.64851 mV |
| 50 ns | 1.800051 V | 27.77857 A | 50.00289 W | 6.70607 mV |

Statistics use time-weighted integration of the final 0.2 ms of a 1 ms run. Step halving changes mean voltage by 0.131 mV and ripple by 0.86%; both explicit acceptance checks pass. This is one bounded load case, not general convergence or controller stability qualification.

## Governing model and power audit

The existing owned native MNA engine solves all electrical states. Native K-coupled inductors are unsupported, so the model explicitly uses a power-conserving ideal transformer: `v_s=n v_p`, `i_p=-n i_s`, n=1/8, implemented using the supported E/F sources. Thus `v_p i_p+v_s i_s=0` independently of loading. Linear primary Lmag is 364.8 µH = 5700 nH × 8². The 5700 nH AL and ±25% small-signal tolerance are supplied core-candidate properties, **not a nonlinear/hot operating inductance or a FEM-derived value**; only the nominal value is exercised here.

The primary bridge is a **prescribed balanced bipolar ±48 V PWM voltage**, 100 kHz full cycle. The ideal synchronous bridge uses supported behavioral source pairs: `v_rect=m(t) v_s`, `i_s=-m(t) i_rect`, with prescribed m=+1/-1 during the respective polarity and m=0 in zero-voltage freewheel intervals. This conserves instantaneous port power, including ideal zero-voltage freewheel. It is not a four-device switch/diode commutation solution. A discrete smooth-switch candidate failed the native Newton solver; it was not presented as a completed result.

Nominal effective active duty is 0.3060620437, tuned for the named load and explicit edge timing. The 64.8 mΩ load follows R=1.8²/50; output is a CPU-like resistive load, not a CPU model. This is **fixed duty, not a feedback-regulated converter**, and does not establish load-step/line-step/startup protection behavior.

Supplied assumptions: primary series resistance 50 mΩ, output L=1 µH with 1 mΩ DCR, C=1000 µF with zero ESR, 1 GΩ secondary reference aid. Secondary copper, switch losses, capacitor ESR/ESL, leakage inductance, parasitic capacitance, deadtime/body diodes, switching loss and core loss are omitted. Do not infer efficiency, a device thermal load or hardware output ripple from the simplified values.

At 50 ns, transformer and ideal-rectifier instantaneous power residuals are each below 1.14e-13 W. An independently reduced backward-Euler energy identity uses right-endpoint source/resistor work, changes in `L i²/2` and `C v²/2`, and numerical dissipation `Σ[L(Δi)²+C(Δv)²]/2`. Residual is 1.18e-17 J over the audit window. Numerical dissipation is reported separately (0.2313 W at 50 ns versus 0.4706 W at 100 ns); it must not be called physical switching or core loss. Simple trapezoid power averages consequently do not close to the resistor sum.

## Physical schematic versus simulation

| Carrier item | Simulated counterpart / deliberate gap |
| --- | --- |
| Q1..Q4 and external J3 driver | Prescribed bipolar source; no actual primary MOSFETs or gate driver solved |
| Q5..Q8 and external J4 driver | Ideal power-conserving rectifier/freewheel source pair; no device commutation solved |
| T1 assembly | Nominal 8:1 ideal transform plus supplied linear Lmag, not solved N97 saturation/loss/thermal |
| L1/C2 | Specified ideal L/C and assumed DCR; placeholders lack sourced ratings, ESR and saturation data |
| C1 input decoupling | Value remains TBD; no DC-link capacitor/bridge-bus dynamics in the ideal source model |
| J2 output and CPU-like load | External 64.8 mΩ resistor; no CPU/package/VRM transient model |

## Native rebuild and evidence

Use installed KiCad Python for `build_carrier.py` followed by `route_carrier.py`, then run native schematic ERC and PCB DRC with schematic parity. The generator recreates the candidate files; do not use it over subsequent hand edits. The local source is firstparty Apache-2.0; the assembly STEP is original geometric demonstration material, and does not redistribute an official TDK CAD model. Core dimensions/material names originate in the separate core study evidence; retain that evidence with a shared pack. See LICENSE, NOTICE and source-provenance.json.
