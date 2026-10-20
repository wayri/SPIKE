<!-- SPDX-License-Identifier: Apache-2.0 -->
# SPIKE analysis gallery

These figures are plots of results executed by SPIKE's checked-in numerical
models and postprocessors. They are documentation analytics, not desktop
screenshots, measured validation, compliance evidence, or production
qualification. The fixtures are original synthetic or analytical references.

## Reproduce the gallery

From the repository root on the recorded Windows development environment:

```powershell
.\.venv\Scripts\python.exe scripts\generate_analysis_gallery.py
```

The script regenerates `data/*.json`, `figures/*.png`, `manifest.json`, and the
public copies in `app/public/help/analytics/`. Each compact data file records the
executed command, the generator and solver source hashes, a request and result
digest, runtime versions, units, model status, limits, metrics, and plotted
series. `manifest.json` records the final data and image hashes.

The checked-in native CFD executable is a local development artifact and is not
redistributed by this gallery. If it is unavailable, build it first:

```powershell
.\.venv\Scripts\python.exe scripts\build_native_airflow.py
```

## Coverage and source examples

| Domain | Gallery figure | Executed model | Existing runnable example or CLI | Status and boundary |
| --- | --- | --- | --- | --- |
| PI | `pi-dielectric-admittance.png` | retained dielectric P1 complex admittance | `python examples/pdn_dielectric_thermal/run_slab.py --plot` | Experimental electroquasistatic retained dielectric; no full-wave or automatic PCB extraction |
| SI | `si-rlgc-line-fields.png` | supplied uniform RLGC network and coherent fields | `python examples/rlgc_line_fields/run_line.py` | Experimental supplied line; no geometry extraction or measured qualification |
| EM | `em-huygens-far-field.png` | closed-box Huygens postprocessor | `python scripts/run_huygens_far_field.py --request examples/em/huygens_dipole_request.json --result build/huygens-dipole-result.json` | Postprocessor over a synthetic dipole boundary fixture; not a Maxwell field solve |
| Thermal | `thermal-two-solid-conduction.png` | two-solid steady P1 conduction with matched contact | `python examples/assembly_field/run_examples.py` | Experimental constant-property solid conduction |
| Hybrid multisolve | `hybrid-electrothermal-convergence.png` | DC conduction and steady thermal fixed point | `python examples/assembly_field/run_electrothermal.py` | Experimental supplied tetra volumes and material laws |
| CFD | `cfd-native-cavity.png` | original native MAC projection, Re=100 cavity | `python scripts/run_cfd.py --engine native --request <request.json> --output <result.json>` | Experimental, isothermal, two-dimensional laminar cavity only |
| CHT | `cht-laminar-channel.png` | sparse finite-volume solid/fluid channel | `python scripts/run_structured_solid_thermal.py --request examples/thermal/laminar_channel_cht_request.json --result build/laminar-channel-cht.json` | Bounded fully developed laminar channel reference; no general assembly CHT |
| Multiboard | `multiboard-coupled-networks.png` | shared two-board R/L harness and thermal RC contact | `python scripts/build_multiboard_acceptance.py --help` | Reduced explicit circuit and thermal networks; no interconnect field or geometry-derived thermal solve |

The source example commands expose the underlying workflows. The gallery script
uses bounded parameter sweeps and richer sampling for documentation plots. The
exact requests and transformations are visible in the generator and bound by
the hashes in each data record.

## Interpretation rules

- A plotted value comes from an executed result or a named direct transform,
  such as complex magnitude, decibels, or an arithmetic mean of returned cells.
- Solver residuals and conservation defects show numerical closure for the
  stated fixture. They do not establish hardware accuracy.
- `experimental`, `approximate`, `postprocessor_only`, and
  `bounded_laminar_channel_reference` are retained rather than promoted.
- The public PNG copies are static help assets. `examples/analysis_gallery/`
  remains the provenance-bearing source of truth.

