# Original antenna fixture: fresh EMerge radiation evidence

On 23 October 2026, the exact SPIKE-owned `examples/emerge/antenna_example.kicad_pcb` and unchanged `examples/emerge/antenna_run.json` were freshly executed through registered contribution **spike.emerge-suite / emerge-radiation**, using separately installed **EMerge 3.0.0a19**. All seven frequencies, 3.0–4.2 GHz, completed with requested 2-mm mesh. Complete complex one-port S-parameters, seven 13×25 angular patterns, complex E-theta/E-phi and normalized cuts are retained.

Status is **completed / unvalidated**. Independent host admission passed against the original design binding. The saved public model-preview source SHA-256 matches the executed source digest. This is traceable execution, not mesh convergence, measured correlation or physical qualification. No solver, fixture or original study configuration changed.

## Chamber boundary

The chamber, antenna, absorbers, table, rack and device-pose controls in `docs/emi-chamber-workflow.md` describe a **visual test setup**. They are absent from this antenna EM mesh. The result does not simulate chamber reflections, absorber properties, receive-antenna transfer functions or receiver detectors. Physical radiated-immunity execution is unsupported here. There is no RE/RI compliance, EMI limit margin, calibrated realized gain or absolute radiated-power claim.

Sphere radius encodes relative E amplitude, not physical distance. Each frequency's sphere/cut is normalized to its own peak; interpolation between saved angular samples is display-only. Pole azimuth is degenerate. Conductors are PEC and dielectric loss is omitted. Preserve `EMERGE_BOARD_MODEL_UNVALIDATED`, `EMERGE_DIELECTRIC_LOSS_OMITTED`, and `EMERGE_EMI_NOT_COMPLIANCE` warnings.

## GUI recording

1. Open the parent native chamber project, or import/select `examples/emerge/antenna_example.kicad_pcb`. Use **EM → Chamber** for the visual room and DUT view.
2. For immediate real-data replay, use the repository root as Python workspace working directory. Open `examples/promo_showcase/em_chamber/radiation/replay_actual_radiation.py`, click **Run**, then **Show in viewport**. This replay was actually executed through `run_python_script`: the full published result was host-admitted and three views published. It reuses retained actual data without another solve.
3. Use **EM → Board + pattern** to show the original board, relative 3D pattern, frequency selection, cuts, S11 and probes. Retain unvalidated warnings. **EM → Chamber** returns to the separate visual room.
4. For a fresh solve use **Settings → Extension manager → EMerge Suite**: trust the bundled extension, check the runtime and select `.venv-emerge3/Scripts/python.exe` or your supported EMerge interpreter. Enter RF/GND, signal pad `51d0c420-4c7b-4da5-b9ec-001000000011`, return pad `51d0c420-4c7b-4da5-b9ec-001000000012`, 3.0–4.2 GHz, seven points, 2-mm mesh. Run **EMerge radiation pattern**. `run_fresh_radiation.py` invokes the same public contribution after GUI trust; set repository-root working directory and raise time limit up to 600 s if needed. That convenience script was not separately executed; the exact contribution/configuration was executed by the existing runner below.

Forum caption: "SPIKE's chamber workspace alongside a real seven-frequency EMerge result from the original patch fixture. The chamber is a visual setup; radiation is unvalidated normalized antenna output, without chamber-physics or RE/RI compliance claims."

## Retained evidence

Under `output/promo-em-chamber-20261023/radiation/`:

- `chamber_antenna_result.json`: full fresh AnalysisResult and angular arrays.
- `admitted-result.json`: independent host-admitted original-design-bound result.
- `import-design.json`, `extension-request.json`: actual imported board and exact registered-contribution inputs, including interpreter.
- `antenna_simulation.py`, `antenna_preview.json`: public generated model source/metadata; source digest matches executed provenance.
- `verification.json`: source/artifact hashes, design binding, seven-frequency/pattern checks, admission.
- `gui-replay-request.json`, `gui-replay-result.json`: real Python child replay, admitted full published result, plots/table and diagnostics.
- `actual_radiation_sphere.png`, `actual_radiation_analytics.png`: visually checked renders of actual arrays, **not app screenshots**. The existing runner also produced `chamber_antenna_plots.png`.

Run from repository root:

```powershell
$env:TEMP = (Resolve-Path output/promo-em-chamber-20261023/radiation).Path
$env:TMP = $env:TEMP
.venv-emerge3/Scripts/python.exe scripts/run_emerge_antenna_example.py --config examples/emerge/antenna_run.json --python-executable .venv-emerge3/Scripts/python.exe --output-dir output/promo-em-chamber-20261023/radiation --output-prefix chamber_antenna
.venv-emerge3/Scripts/python.exe output/promo-em-chamber-20261023/radiation/retain_admit.py
.venv-emerge3/Scripts/python.exe output/promo-em-chamber-20261023/radiation/verify_gui_replay.py
.venv-emerge3/Scripts/python.exe output/promo-em-chamber-20261023/radiation/render_actual.py
```

The replay/render commands do not solve again. Parent native-package preparation owns chamber setup/result persistence.

## License and credit

The patch is an original SPIKE-owned **Apache-2.0** fixture, documented in `examples/emerge/gui_workflow/README.md`. Scripts/adapter/generated model source retain Apache-2.0 and existing copyright/notices. Credit **SPIKE — Yawar B (wayri) and contributors**. Generated source contains first-party adapter/model data, not upstream solver implementation.

Credit **Robert Fennis / EMerge** for the separately installed solver. Do not label its runtime Apache or uniformly MIT: `THIRD_PARTY_NOTICES.md` records GPL-2.0-or-later Gmsh-derived components and a CC0 materials database. EMerge and its runtime/dependencies are not redistributed here; consult their original licenses for separate runtime distribution. This example retains first-party fixture/model/result evidence and documentation.
