# Temperature history from the viewport

With thermal results displayed, use the All, Parts or Nets selection filter as
usual. The result overlay does not consume ordinary object selection.
Right-click a board point, component or retained STEP model and choose
**Thermal results > Plot temperature vs time**. The popup supports zoom, pan,
image/data copying and Escape to close. Axes are seconds and degrees Celsius.

The plot reads retained transient samples from the active thermal result:

- Board points use the saved grid cell and layer, with board occurrence checks.
- Components use their own retained compact thermal nodes, including separate
  junction/case curves when present. A board temperature is not substituted for
  an unsolved component.
- Solved STEP bodies use retained solid node histories and the saved geometry
  ownership ranges. Select a node in the thermal volume viewer, then right-click
  its plot to open that exact node's history. Whole-body requests expose individual
  retained node curves rather than an inferred uniform body temperature.

A steady-state result, missing time samples, mismatched board occurrence, missing
solid ownership or incomplete history produces an explanation. Run a transient
study including the target and retain its samples. Lines only connect saved
samples; they do not add solved time steps. A board-grid result remains a board
approximation and does not establish that package solids were solved.

## Verification

`node app/scripts/test-thermal-probe-history.mjs` checks exact board, component
and solid node extraction, malformed histories, duplicate identities and board
occurrence isolation. Desktop checks include TypeScript, the architecture and
button guards, viewport context, thermal rendering and plot interactions.

`app/scripts/thermal-interaction-preview.html` exercises the production WebGL
viewport and history popup using a retained Sailor Hat board with authoritative
KiCad models. Its temperature histories are synthetic interaction fixtures,
explicitly labeled in the UI; they are not numerical validation. The live check
selected L701 and the /Protection/Vin_CM trace with the thermal overlay active,
opened the L701 curve (25, 40, 55 degrees Celsius at 0, 5, 10 seconds), opened a
board-cell curve, and closed the modal with Escape at a narrower window size.
