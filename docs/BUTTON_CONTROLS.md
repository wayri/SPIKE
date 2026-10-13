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
reserved, keyboard-accessible command panel. Submenus replace its current list;
Back and Escape move to the parent. All existing menu and toolbar handlers are
discovered from their React descriptors rather than copied into another command
registry. Dynamic extension visibility and disabled states remain authoritative.

The viewport keeps only 2D/3D, Layers, Fit and View. Camera, selection filters,
model toggles, result display and advanced workspace commands open on demand.
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
