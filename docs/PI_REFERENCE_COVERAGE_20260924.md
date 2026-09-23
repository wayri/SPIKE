<!-- SPDX-License-Identifier: MIT -->
# PI reference coverage and release acceptance

Date: 2026-09-24. This maps the user-supplied PI references to SPIKE's current
contracts and observable work. It is a requirements and evidence ledger, not a
claim that the cited vendors' solvers, images, or UI are implemented in SPIKE.
No external code, graphics, or test data were copied. The Zuken link was supplied
twice; both YouTube pages were inaccessible during this review, so they cannot
support a video-specific requirement or visual-parity claim.

| Priority | User flow and result to show | Current SPIKE evidence | Remaining acceptance gate |
| --- | --- | --- | --- |
| P0 | Define each rail, source, return, loads, operating current, and voltage/drop/current-density budget; retain exact pad and layer ownership. | [PI user guide](USER_TASK_PI_RELEASE.md), [power tree benchmark](POWER_TREE_BENCHMARK.md), and approximate copper DC in [solver status](SOLVER_STATUS.md). | A real-board source-to-load scenario must complete with reviewed terminals and a persisted operation/result ID. Reject missing return, ambiguous pins, and incomplete conductor geometry. |
| P0 | Review DC voltage, drop, current, current density, copper loss and via/neck hotspots on aligned copper layers; probe the original source value with units and source identity. | [Result visualization limits](RESULT_VISUALIZATION_AND_LIMITS.md), [trace graphs](TRACE_RESULT_GRAPHS.md), and [results verification](RESULTS_WORKBENCH_VERIFICATION_2026_09_20.md). | Verify actual solved-board geometry alignment, layer independence, probe value, source/load extrema, and mesh convergence. Synthetic rendering fixtures establish presentation only. |
| P0 | Show blocked/failed/approximate/validated states, assumptions, stackup, mesh quality, source/worker version, warnings, and diagnostic details in every result and report. | [PI release gate](PI_RELEASE_QUALIFICATION.md), [solver status](SOLVER_STATUS.md), and the failed-result trace guard in `app/src/traceResultPlots.ts`. | A failed or `solved=false` run with partial samples cannot appear as a solved heatmap, graph, favorable score, or report conclusion. Check all consumers and saved/reopened results. |
| P1 | Choose an explicit power/return observation port and view complex PDN impedance versus frequency, including phase, target impedance and violations at load pins. | Experimental PEEC AC and [PDN screening](PDN_SCREENING.md). The trace graph now shows the reviewed target for the matching result and net, while source samples retain their identity. | Physically passive, converged and independently correlated multiport extraction with explicit return and materials. Real-board AC remains blocked by negative-energy modes; do not render its diagnostic samples as qualified impedance. |
| P1 | Compare declared decap banks and candidate locations with C/ESR/ESL/count and mounting assumptions, before/after target plots, resonance/antiresonance locations and per-candidate status. | [PDN screening](PDN_SCREENING.md) has direct-port, explicit-path and bounded multiport alternatives. | Show model and provenance for each alternative; reject mismatched frequency grids or invalid ports. Do not label approximate screening as optimized physical placement. Validate ranking against a measured or independent board reference. |
| P1 | Define load-step/source waveforms; inspect transient rail minimum, peak/ripple and time-linked board frames and probes. | [Transient PI](TRANSIENT_PI.md) supports fixed-step experimental geometry PEEC with step, pulse and PWL inputs. | Passive matrix admission, convergence, waveform/reference checks and source/load limit evaluation. Negative inductance modes return an explicit failure and no waveform. |
| P2 | Link copper loss to thermal, noisy supply to SI/EMI, and compare design revisions or operating scenarios. | Separate thermal, SI and EMI surfaces exist; [solver status](SOLVER_STATUS.md) distinguishes their validation states. | Explicit coupled model and evidence, shared result identity and units, synchronized geometry, and independent comparison. Do not put EMI sections in a PI-only report or infer coupled results from an isolated PI run. |

Presentation acceptance across the rows: a consistent docked results workbench;
optional detachable plots for multiple monitors; PI-specific controls and report
sections; net/layer and returned quantity selection; readable color scale and
units; exact hover samples; trace and net comparisons; status-aware CSV/HTML/PDF
output. HTML may tab by net; print/PDF must include all nets in a linear document.
Decimation and display interpolation must be labeled and never change solver
samples. See [engineering reports](ENGINEERING_REPORTS.md).

## Implementation checkpoint (2026-09-24)

The results panel now exposes a scoped DC review using original returned
voltage, drop, copper-density and via-density samples, including limit states,
geometry identity and approximate-model labeling. A PDN review is tied to the
exact source analysis ID and rejects failed sources, mismatched nets/sweeps
and incomplete candidates. HTML report admission excludes partial values and
plots from failed or blocked solves while retaining their diagnostics. Focused
fixtures verify these presentation guards. These changes close the UI
admission portion of the P0/P1 rows; they do not close physical board
correlation, source/load terminal measurement, passivity or convergence gates.

The first PI release is still **blocked** by the six native workflow gates in
[PI release qualification](PI_RELEASE_QUALIFICATION.md), including real-board
AC/transient and coupled solver evidence. Reference coverage does not relax any
gate. An engineering candidate may carry explicit approximate or experimental
features only within its separately approved source scope, with those labels
visible in the UI and release notes.

## Sources reviewed

- [Ansys, What is Power Integrity?](https://ansys.synopsys.com/en-in/simulation-topics/what-is-power-integrity): rails/returns, DC loss, ripple, target impedance and decoupling.
- [eCADSTAR, Power Integrity in PCB Design](https://www.ecadstar.com/en/blog/power-integrity-in-pcb-design/): voltage drop, resonance, ground bounce, decaps and layout iteration.
- [Zuken, Mastering Power Integrity](https://www.zuken.com/en/blog/mastering-power-integrity/): PDN design, decoupling and design flow.
- [Altium, Power Integrity Analysis](https://resources.altium.com/p/power-integrity-analysis): DC/AC analysis and source-to-load review.
- [PCB Hero, DC Analysis and Power Integrity](https://www.pcb-hero.com/blogs/lickys-column/dc-analysis-and-power-integrity-in-pcb-design): DC drop/current-density interpretation.
- [WonderfulPCB, Power Integrity Simulation Analytics](https://www.wonderfulpcb.com/blog/power-integrity-simulation-analytics-pcb-design/): PDN and analysis presentation.
- [Power Electronic Tips, Power Integrity Analysis FAQ](https://www.powerelectronictips.com/power-power-integrity-analysis-high-speed-digital-faq/): target impedance and high-speed PDN context; direct page load was unavailable and only search-index text was accessible.
- User video references: [NOGw-M-DPN8](https://www.youtube.com/watch?v=NOGw-M-DPN8&t=26s) and [ZJsKYZO8dyE](https://www.youtube.com/watch?v=ZJsKYZO8dyE&t=69s). Both page/transcript fetches failed during review; no content from them was relied upon.
