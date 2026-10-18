# Button and control standard

SPIKE desktop controls use `app/src/buttonStandard.css`. The application entry
point and every first party Vite preview with interactive controls must import
that stylesheet. It reuses `tableTheme.css`, so controls follow professional
dark, light, system, and high contrast palettes.

## Baseline

Native buttons, button-like inputs, text fields, selects, text areas, and
elements with `role="button"` receive an explicit font, minimum height, padding,
border, surface, text color, pointer state, disabled state, and keyboard focus
ring. File picker buttons and checkbox, radio, and range accents also use the
theme. Shared geometry and state selectors use `:where(...)` and therefore have
zero specificity. The font reset uses ordinary element specificity so it wins
the older global inherited-font rule. A scoped component class can still define
necessary typography or geometry without resetting the common interaction
states.

Use a semantic `<button type="button">` whenever possible. A non-native
`role="button"` must also implement keyboard activation, focusability, and
`aria-disabled` behavior in its component.

## Variants

Use either the class or equivalent `data-spike-control` value:

- `spike-control--primary`: the main commit or run action in a surface.
- `spike-control--danger`: a destructive action after its workflow has applied
  the required confirmation or recovery behavior.
- `spike-control--compact`: a dense text control with a 24 px minimum height.
- `spike-control--icon`: a square icon control. It still needs an accessible
  name through visible text, `aria-label`, or `title` where appropriate.
- `spike-control--bare`: removes the surface and spacing for a deliberate
  embedded control while retaining focus and disabled behavior.

Existing icon buttons, ribbon cells, editor gutters, table controls, viewport
gestures, and dock tabs are deliberate specialized variants. Their scoped
styles may override size, layout, border, and background. They must preserve a
visible `:focus-visible` state, disabled behavior, and theme-readable text.

## Guard and boundaries

Assembly view tools use `AssemblyIconToolbar.tsx`: a 17 px icon, a short visible
label, and a full accessible name and tooltip. Keep toggle state in
`aria-pressed` and use native disabled buttons when an occurrence is required.
Camera actions belong in the top toolbar. Placement, visibility and section
fields belong in a reserved inspector, with help beside the view rather than
overlapping its controls. The assembly preview also uses a left panel rail;
at narrow widths its inspector stacks below the canvas. See
[assembly CLI workflows](ASSEMBLY_CLI.md) for saved structure edits.

Run `node scripts/test-assembly-icon-toolbar.mjs` from `app` when changing this
shared toolbar. It checks names, tooltips, visible mini labels, action routing,
toggle semantics and disabled controls.

Run `npm run test:button-standard` from `app`. The guard verifies application
entrypoint coverage, checks every first party `scripts/*preview.tsx` containing
a button for the shared import, and validates the required states and token-only
control rules.

Generated engineering report and print HTML is a separate document with
self-contained report CSS. Third party web content is outside the SPIKE style
boundary. Neither may be rewritten to import application CSS. Canvas and SVG
gesture targets are checked by their owning interaction tests; when they expose
`role="button"`, their component remains responsible for keyboard activation.

## Focus workspace

The main shell uses the Graphite + Teal professional-dark tokens. Menu opens a
small, keyboard-accessible popup which can also detach into a native window. Submenus replace its current list;
Back and Escape move to the parent. All existing menu and toolbar handlers are
discovered from their React descriptors rather than copied into another command
registry. Dynamic extension visibility and disabled states remain authoritative.

The viewport keeps 2D/3D, Layers, Fit and View, plus a compact context quick-tools
bar in a reserved row. Its More popup exposes the complete context action catalog. Camera, selection filters,
model toggles, result display and advanced workspace commands open on demand.
The bar shows the active workspace and selection, with teal tool icons and
bounded horizontal overflow. Drag its grip to reposition without changing the
grab point. On the grip, Left/Right moves in small steps and Home/End aligns
to an edge; on tool buttons, those keys navigate the available actions.
Shared `--spike-popup-*` tokens define opaque graphite surfaces, subtle borders,
soft corners and shadows for context menus, command popups, search, notifications
and measurement cards. Light and high-contrast settings retain their own palette.
The navigator, studies, setup, managers and results share one reserved tool slot.
Hide keeps inputs mounted; a tool closes through its existing Close/Apply/Discard
flow. Expand/Restore and a bounded resize handle support large tools. Native
secondary windows remain explicit actions. See WORKSPACE_PANELS.md.

## Table and menu density

Shared tables start with compact row spacing while retaining 12 px text and
28 px column headers. Compact toggles expanded row spacing. Keyboard Help
reveals the editable/dropdown/locked field guide on demand. Embedded tables
can omit duplicate tools with showTools=false while retaining bounded rows,
pagination and keyboard cell navigation.

The probe dock combines formula, export, detach and close commands into one
header. It shows one empty-state instruction, instead of stacked empty panels.
Layers on the viewport toolbar opens the floating layer manager. Its docking
controls and close button remain available; View > Layer manager also reopens it.


### Context quick tools

The movable compact bar at the top of the viewport follows the selected object,
board occurrence, workspace, saved result admission, and active job. Its short
icon buttons reuse the workspace context handlers. Availability is resolved
again on activation; a missing or disabled action does not run. PI and SI
buttons open existing setup/preflight workflows. Stop appears during a job.
More retains all context actions and their reasons when unavailable. Move the
bar with its grip, or focus the grip and use the left/right arrow keys.

Presentation tokens apply to first-party UI surfaces and popup controls. Semantic
warning/error colors and engineering plot/field scales retain their meanings.


### Responsive editor surfaces

Project and net managers use compact action groups and named container queries.
Narrow net catalogs retain all metrics as labeled cards. Study, SPICE, EMI, flex
and script-result editors adapt to their actual panel width rather than the
main monitor width. Table columns which require side-by-side editing remain
available in bounded horizontal scrolling. Temporary confirmations stay inside
their editor pane. Native floating panels use the OS title-bar close control;
closing that frame returns its current draft to the dock.

Run `test:quick-tools`, `test:responsive-managers`, `test:table-theme` and
`node scripts/test-panel-responsive-layout.mjs` from `app`, plus the focused
workflow tests for the changed editor. Native linked-window qualification is
available with `--panel-popup-qualification`; it uses an isolated presentation
route and does not open a project or run a solver.
