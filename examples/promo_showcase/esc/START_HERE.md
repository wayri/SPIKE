<!-- SPDX-License-Identifier: Apache-2.0 -->
# ESC and SPIKE Studio recording pack

This pack pairs Benjamin Vedder's published VESC hardware with executed SPIKE
board studies and native SPIKE Studio circuits. Open the projects in SPIKE and
record locally. Solver outputs are retained under EVIDENCE; they are not a video
or a claim that the desktop was interactively exercised during preparation.

## Start with Studio

1. Launch internal SPIKES Studio. Select the native engine documented in
   `studio/README.md`; the packaged main worker library passed these examples.
   The older circuit-worker library lacks the dependent-source ABI required by
   the ideal sensor amplifier examples. This pack contains no native DLL.
2. **File > Open** `studio/backemf_sensing.spksch`. Show the actual wired circuit,
   probes and source; run its transient, then show the dashboard scopes.
3. Open `studio/current_sensing.spksch`, run and inspect the 20 mV shunt and 1 V
   amplifier response. Open `studio/gate_miller_ringing.spksch` for the fast
   transient and cursor measurements. These three circuits use illustrative
   values; actual board-derived sensing studies live in `analytics`.
4. Open `studio/two_wheeler_dashboard.spksch`. Review the embedded C controller,
   compile using Studio's trust workflow, attach to Continuous and run closed
   loop. In Dashboard Run mode set Throttle to 0.2 and Send, then apply Brake.
   Show current, speed and back-EMF while adjusting the controls.

The last project is an averaged PMDC equivalent. The sensing waveform is a
supplied source. These demonstrate circuit execution, probes, dashboards and
compiled controller interaction; they do not run VESC firmware, three-phase FOC
or a field-coupled motor. Board studies and Studio circuits are separate models.

## Board and Python workspace

Open the thermal native `.spike` project described in `thermal/README.md`; it
retains the board and the exact executed thermal setup. Inspect the six physical
MOSFET locations. Follow that README for available steady/transient variants
and the layer-stack assumptions. The upstream four-layer board has no explicit
physical stackup; an assumed stack, if supplied, is a modified example, not
verified fabrication data.

For the original board choose **File > Import** and
`VESC_HARDWARE_CC_BY_SA/BLDC_4.kicad_pcb`. In **Tools > Python workspace**, Files >
Open scripts folder, choose this pack's `analytics` folder. Open the numbered
templates and **Ctrl+Enter** to execute. Follow `analytics/README.md` for the
actual DC/AC PI/sensing models and their published views. They invoke registered
SPIKE workers; their documented reduced networks are not automatic full-board
extraction. The template validation guards protect against running on another
board. Review supplied parasitics and exclusions before changing values.

The source README/BOM labels the release 4.12; the PCB's internal title block
still says “BLDC Driver 4.6”. The exact source revision and hashes identify the
actual file without silently correcting upstream metadata.

## A short edit using actual operations

Prepare/run studies before recording and record each action as a separate
5–10 second take. Keep the full uninterrupted original captures. Remove idle
loading/compilation from the public edit; disclose accelerated playback if used.

| Time in a 60 s edit | Actual SPIKE capture | Suggested overlay |
| --- | --- | --- |
| 0–8 s | Board viewport, rotate and select one MOSFET | Open hardware → explicit simulation inputs |
| 8–18 s | Thermal setup, solved board temperature and comparison | Supplied losses; stated cooling assumptions |
| 18–28 s | Python workspace Run, PI impedance and sense-channel AC views | Native circuit solver; reduced networks |
| 28–38 s | Studio board-derived sensing circuit, probes and waveform | Actual schematic values where identified |
| 38–47 s | Studio fast gate-loop waveform and cursors | Illustrative linear gate-loop model |
| 47–58 s | Studio C controller dashboard: throttle, then brake | Averaged PMDC closed loop |
| 58–60 s | SPIKE title and attribution | Source/license credit; link to examples |

Motion graphics can label the captures and transition between them. Keep model
scope labels visible; do not turn supplied excitations into “measured back-EMF”,
use steady fields as transient frames, or label independent studies as a coupled
ESC solution. The broader showcase pack retains separate FEM motor examples;
they are not driven by this controller.

See `ATTRIBUTION.md` before posting the board or its derivatives. The hardware
is CC BY-SA 4.0; original SPIKE scripting/illustrative examples have their own
Apache notices. No upstream endorsement is implied.

## Rebuild

From the SPIKE repository, use each area's documented preparation/verification
script, then run `.venv/Scripts/python.exe examples/promo_showcase/esc/package.py`.
The delivered ZIP has a SHA256.json file manifest and was checked by decompression
and byte hashes. GUI recording and final video production remain manual.
