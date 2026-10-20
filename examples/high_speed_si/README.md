# High-speed SI and multiboard PI reference studies

> **Public evidence boundary:** Paths marked as unbundled local records identify generated developer-run evidence that is not shipped in the public source. The historical observation remains provisional and does not establish release qualification; reproduce and review it before relying on the claim. See the [release local-evidence boundary](../../docs/validation/RELEASE_040_LOCAL_EVIDENCE.md).

Executed 2026-10-10 using SPIKE integrated workers and its configured openEMS extension. These are original numerical reference models. No board, harness model or PHY was supplied for hardware qualification.

## Reports and saved studies

- Interactive report with section navigation, 3D E/H samples and exact probes (unbundled local record: `../../output/high-speed-si/reports/index.html`)
- Ethernet, LVDS and SerDes PDF (unbundled local record: `../../output/high-speed-si/reports/protocol-si.pdf`)
- Harness and multiboard PI/SI PDF (unbundled local record: `../../output/high-speed-si/reports/harness-multiboard.pdf`)
- Interboard field PDF (unbundled local record: `../../output/high-speed-si/reports/interboard-fields.pdf`)
- Native projects: 1G (unbundled local record: `../../output/high-speed-si/projects/ethernet_1g.spike`), 10G (unbundled local record: `../../output/high-speed-si/projects/ethernet_10g.spike`), 100G lane (unbundled local record: `../../output/high-speed-si/projects/ethernet_100g.spike`), LVDS (unbundled local record: `../../output/high-speed-si/projects/lvds_1g.spike`), SerDes (unbundled local record: `../../output/high-speed-si/projects/serdes_32g.spike`).

Open a native project with File > Open file or project. Its retained `analysis.si.latest_channel_result` was verified through the actual project read handler. Alternatively load `protocol_results/<case>.json` from HF / SI > Source-to-receiver workflow > Load setup/result. Abstract differential artwork illustrates placement; it is not the geometry from which the supplied RLGC was extracted.

Open the HTML directly in a browser; Plotly is bundled locally. Rotate/zoom the field and harness scenes, select E/H and frequency, and click a saved sample or use its index to probe exact complex vectors. Conductor probes show actual lumped DC current and loss; signal conductors absent from the DC model explicitly remain unsolved. No spatial voltage distribution is invented. The harness display compresses the longitudinal aspect ratio for readability.

## Results and applicability

| Study | Executed model and observation |
| --- | --- |
| 1G | 1000BASE-X host serial, 1.25 GBd; finest eye height 0.797998 V |
| 10G | 10.3125 GBd NRZ; finest eye height 0.765438 V |
| 100G | One uncoupled 25.78125 GBd lane of a four-lane architecture; finest eye height 0.589838 V |
| LVDS | Illustrative 1 GBd differential model; finest eye height 0.701525 V |
| SerDes | Generic 32 GBd NRZ; finest eye height 0.509954 V |
| Harness PI | Two board occurrences, 0.6 m power/return wires, 12 V source and 4 A remote load: 11.834483 V load, 0.662069 W wire loss |
| Harness coupled SI | Four round signal wires above an ideal reference plane; peak differential NEXT -35.245 dB and FEXT -36.574 dB over 0–250 MHz |
| Interboard fields | Actual four-excitation, four-port openEMS box fixture, 0.2–3 GHz; completed in 472.23 s and passed bounded numerical sanity gates |
| 3D E/H | Separate A.near excitation, 23 x 14 x 12 native cell-interpolated positions at 0.5, 1.5 and 2.5 GHz; finite data and exact HDF5 sample equality |

The channel transfer agrees with an independent ABCD oracle to less than 7e-15 absolute error. This checks implementation for these uniform lines, not hardware accuracy. LVDS initially failed the unchanged 5 mV successive-grid criterion; further 4097/8193-point refinement reduced the final change to 0.386 mV. Saved base-grid eyes and finest-grid scalar results are labeled separately.

The field network has maximum sampled singular value 1.000344 and reciprocity error 0.003095; both satisfy existing 0.02 sanity tolerances. Duration, PML and mesh convergence or measured correlation have not been established. The first 300-second field attempt timed out and remains preserved; the successful retry only increased the time allowance to 600 seconds. Spatial field amplitudes are raw unnormalized Gaussian-pulse DFT coefficients, not calibrated 1 V/1 W steady-state fields.

No BASE-T copper PHY, PCS/FEC/COM/BER compliance, nonlinear device/IBIS-AMI behavior, coupled four-lane 100G eye, arbitrary cable geometry extraction or real-board qualification is claimed. The GUI supports the uniform-harness workflow; coupled MTL uses the integrated worker but has no dedicated desktop panel. The HTML is the supplied 3D evidence viewer, not a new native viewport feature.

## Reproduction

Use a fresh output directory for harness or field reruns; preserve original evidence.

```powershell
.venv/Scripts/python.exe examples/high_speed_si/run_protocol_cases.py
.venv/Scripts/python.exe examples/high_speed_si/package_protocols.py
.venv/Scripts/python.exe examples/high_speed_si/harness/run_interboard_harness.py --output-dir output/high-speed-si/harness-rerun
.venv/Scripts/python.exe scripts/multiboard_em_acceptance.py --output output/high-speed-si/field-rerun --timeout 600
.venv/Scripts/python.exe scripts/multiboard_em_acceptance_interference.py output/high-speed-si/field-rerun
.venv/Scripts/python.exe examples/high_speed_si/field/run_interboard_field_capture.py --help
.venv/Scripts/python.exe examples/high_speed_si/render_reports.py
```

The report generator reads the retained current evidence locations; it does not run solvers. Requests, hashes, checks, native port histories and HDF5 dumps accompany each case. See [protocol details and primary references](protocol.md), [harness methods](harness/README.md), and [native field capture](field/README.md).

## Verification scope

Focused existing SI/harness checks reported 53 and 48 passing tests respectively; architecture validation passed. All PDF pages were rendered and reviewed; table pagination was repaired. Browser DOM verification loaded 14 plots, switched to the 1.5 GHz magnetic frame, probed saved sample 1932, and returned the power wire current/loss without console errors. Browser screenshots were blank despite populated DOM/plots, so rendered browser appearance and actual 3D click-picking were not visually verified. Native desktop interaction with these packages was not exercised; package retention was checked through the actual backend reader. Hardware-specific follow-up requires actual boards, interconnect geometry and endpoint models.

## Plot reading and presentation checks

The interactive report uses explicit GHz, dB, V, UI and mm axis titles,
unit-bearing hover values, and a horizontal raw E/H color scale (V/m or A/m).
Each plot section explains its normalization, port mapping and interpretation.
Recorded channel, harness and field check outcomes are shown beside the data;
the field sanity screen remains separate from physical accuracy qualification.
Raw diagnostic JSON can be expanded below the summaries.

The report titles now use the object schema required by bundled Plotly 3.7.0.
Two focused report tests execute generated JavaScript with a plotting stub and
check all plot axis contracts, E/H units, exact sample probes, invalid indices,
and unavailable validation evidence. Architecture and documentation checks pass.
Regenerating the report preserved all numerical payload values; only explanatory
metric rows changed. Report manifest hashes were refreshed and verified.
The browser tool rejected this local `file://` report URL, so live browser visual
acceptance of this revision remains unverified. Refresh the report in your browser
to see the revised plots.

### Field slice navigation

The PDF now shows separate full-width electric and magnetic heat maps, with
XY and XZ planes through the largest saved sample at 1.5 GHz. Each slice states
its physical position and the color scale's power-of-ten multiplier. The legacy
`native-volume-fields.png` overview is regenerated with these slice figures.

The HTML defaults to a native 2D slice. Select XY, XZ or YZ, then use the slider,
arrow keys, Previous/Next slice or Go to peak. Select frequency and E/H independently.
Hover a cell to read the raw norm; click it to inspect the exact retained vector.
The color range stays fixed across slices at the selected quantity/frequency.
The optional 3D volume remains available through Field view. A PDF is static;
use the HTML report for navigation and probes. These are native sample maps,
not reconstructed PCB surface fields or physically qualified amplitudes.

Four focused tests pass, including coordinate ordering, all three slice planes,
bounded navigation and peak selection. Generated PNG slices were visually inspected;
live HTML visual acceptance remains blocked by the browser tool's local-file policy.

## Engineering report interaction

Regenerate the offline HTML and three PDFs with
`python examples/high_speed_si/render_reports.py`. This reads saved evidence;
it does not rerun a solver.

- Start with the result review navigator. Recorded reference checks, design
  acceptance limits, and physical accuracy are separate. Unspecified limits
  remain unspecified; no compliance margin is invented.
- Hover frequency curves for a common frequency cursor; click to pin a
  measurement with units. Eye traces use the nearest-point cursor to avoid
  a long list of overlapping traces. Drag to zoom; double-click to reset.
- In the assembly view, use orthogonal slices with translucent model outlines.
  Click a native sample, or enter its index, to see coordinates, frequency,
  complex vector components, norm and containing model region in the inspector.
  A cyan cross marks the selected sample when it is on the displayed plane.
  The exact JSON payload remains available in an expandable section.
- Use **Shared across frequencies** for comparisons within one field quantity;
  **Selected frequency** emphasizes the structure in that frame. E and H retain
  separate units and ranges. Smoothing changes display only.
- The protocol PDF begins with a compact refined-eye review sheet. Bookmarks
  and its contents lead to setup, plots and recorded checks.

Implemented scope is the generated high-speed SI reports. It does not establish
full desktop cross-probing, commercial feature parity or new physical validation.
The captured geometry is a two-substrate/trace box model, not complete PCB artwork.

