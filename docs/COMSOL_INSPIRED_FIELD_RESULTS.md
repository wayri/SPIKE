<!-- SPDX-License-Identifier: Apache-2.0 -->
# Coupled field results: reference and implementation boundary

Owner direction, 26 October 2026: use COMSOL as the primary inspiration for
multiphysics workflows, published formulations and result presentation.
Simbeor remains a useful secondary reference for interconnect field inspection.
This is a product and verification brief, not a claim of numerical equivalence.

## Public references reviewed

- [COMSOL: Conjugate Heat Transfer, Nicolas Huc, 6 January 2014](https://www.comsol.com/blogs/conjugate-heat-transfer):
  solid conduction, fluid energy transport and continuity at the interface;
  electronics cooling and heat-exchanger result presentation.
- [COMSOL: Using Plots to Visualize Results](https://www.comsol.com/video/plots-visualize-results-comsol-multiphysics):
  volume, surface, line, vector, slice, contour, isosurface and streamline
  presentation. Public page descriptions reviewed; not a claim of watching
  every training video.
- [COMSOL 6.4 CFD Results](https://doc.comsol.com/6.4/doc/com.comsol.help.cfd/cfd_introduction.02.11.html):
  separate velocity, pressure and streamline result views.
- [COMSOL: Assembly Meshing for CHT](https://www.comsol.com/model/using-assembly-meshing-for-conjugate-heat-transfer-modeling-69901):
  assembly mesh preparation as a separate prerequisite to coupled results.
- [Simbeor overview, December 2019, pages 8 and 11](https://www.simberian.com/Presentations/SimbeorOverview_Dec2019.pdf):
  geometry-related electric, magnetic, current and power-flow views and
  network-result tools. This dated overview is not a current capability audit.
- [User-supplied SimScale CHT video](https://www.youtube.com/watch?v=Js99DZcY40g):
  title/link identified; the retrieval did not expose a transcript. No claims
  about its detailed contents are used as implementation evidence.

Reference images supplied by the owner illustrate the intended result, but
are not redistributed in SPIKE. No proprietary implementation, example model,
mesh, branding or artwork is copied. New presentation code is independently
authored against SPIKE's admitted data contracts.

## Required experience

1. Select the geometry participating in the study, materials, sources, flow
   conditions and interfaces. Visible CAD alone does not create a flow obstacle.
2. Inspect the fluid domain and the solid regions used by the solver. Show
   declared proxies and missing detailed geometry explicitly.
3. Run the admitted coupled model, retaining convergence, conservation,
   geometry identity and saved times with the results.
4. View solid temperature together with fluid streamlines. Select air
   temperature independently of solid temperature; keep units and scales clear.
5. Use transparency and cuts to inspect interior regions. Inspect exact saved
   samples and their coordinates. Hold the color scale fixed when comparing
   time frames, with explicit manual limits for close inspection.
6. Click Play to review saved transient frames. Display physical time.
   Direction markers on instantaneous streamlines are a presentation aid,
   not particle trajectories or a replacement for solving a transient flow.

## Capability distinctions that must survive the UI

| Display or physics target | Evidence required |
| --- | --- |
| Colored volume samples | Returned scalar values, coordinates and units; bounded decimation disclosed |
| Solid surface temperature | Boundary mesh and boundary solution mapping; cell voxels must not be called a surface reconstruction |
| Airflow around components | Fluid domain excludes the participating solids; native paths and interface/mesh checks retained |
| Combined solid/fluid result | Explicit common coordinate registration and matching saved time; no pairing by filename or nearest time |
| Air temperature | Fluid energy solution, not solid temperatures copied into air |
| E/H field lines | Corresponding returned vector field or supplied field curves; voltage or SI victim noise does not establish E/H |
| EM power flow | Compatible complex E and H, frequency and excitation convention, plus a reviewed derived-field implementation |
| Recirculation and turbulent wakes | Appropriate momentum model, boundary-layer resolution, convergence and validation; decorative curves are insufficient |
| Transient CHT | Solid and fluid energy storage and time-coupling evidence, not an animated steady result |

The existing layered board thermal model remains approximate and distinct
from geometry-resolved CHT. Current component-cuboid CFD evidence does not
qualify arbitrary STEP packages. Thin leads and transformed retained solids
still have open meshing/admission problems in the October 2026 evidence.

## Component dissipation and board copper loss

The owner clarified that component volume dissipation heats the package,
board and air, while copper losses are an additional source. Treat these as
separate conserved source terms. A visual STEP shell alone does not specify
the die, internal materials, loss distribution or package-to-board contacts.

The current assembly-airflow adapter accepts explicit watts per solid region
and deposits `P / V` in W/m3. The retained-volume electrothermal workflows
instead map computed electrical losses to explicitly selected solid cells;
see [volume loss mapping](MULTIBOARD_VOLUME_ELECTROTHERMAL.md) and
[assembly electrothermal coupling](ASSEMBLY_ELECTROTHERMAL.md). These routes
are not interchangeable: displaying copper does not compute its losses,
and the current bounded CHT demo does not include a board-current loss solve.
Do not deposit the same electrical loss again as a user background source.

The inspected sibling `kiWay/quick_therm_plugin` presentation uses translucent
board context and prefers solved thermal-layer patches, with separate
component-junction markers. Its junction interpolation is explicitly
illustrative. SPIKE adopts the readability principle without copying sibling
implementation or treating interpolated junction colors as solved package
surface temperatures. Preserve exact saved samples and their units.

The 0.020 s saved CHT example is a short startup demonstration: the solid
temperature range is only about 25.000--25.266 C. It must not be presented as
steady cooling performance or artificially warmed to make an attractive image.

## Mathematics and acceptance

The solver-folder [mathematics and references](../python/spike_core/solvers/MATHEMATICS_AND_REFERENCES.md)
catalog maps implementations to equations, assumptions and detailed evidence.
Use [numerical method evidence](NUMERICAL_METHOD_EVIDENCE.md) before changing
physical formulations. Published vendor demonstrations guide requirements;
independent analytical cases, refinement studies and physical measurements
establish SPIKE accuracy within explicitly stated limits.

For each new geometry-resolved CHT route, retain mesh validity, interface
orientation, mass balance, heat balance including stored energy, time-step and
mesh refinement, and a reference case. Report missing gates independently of
successful rendering. Phase change, radiation, compressibility, turbulence,
moving machinery and arbitrary CAD import are separate capabilities, not
automatically included because a CHT result can be displayed.
