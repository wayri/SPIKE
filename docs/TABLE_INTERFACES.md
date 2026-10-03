# Table interfaces

SPIKE's active React desktop uses `DataTable` for tabular engineering data.
The component gives tables a consistent local viewport, row search, density
control, pagination, and keyboard movement without taking ownership of the
engineering data or its edits.

## Ownership and API

`app/src/DataTable.tsx` owns the table toolbar, viewport, focus state, paging,
and composition of the native `table` element. `app/src/dataTableModel.tsx`
owns the pure row grouping, displayed-value search, paging, and body rendering
helpers. `app/src/spreadsheetGrid.ts` owns keyboard movement between editable
cells. Layout styles belong to `app/src/DataTable.css`; inherited palette tokens
and theme selection belong to `app/src/tableTheme.css`.

`TableIdentityInput.tsx` stages editable identifiers so each keystroke does not
rename and recreate its row. Enter or leaving the field applies the identifier;
Escape restores its previous value. Adapters reject blank or duplicate IDs
before invoking the existing update callback. Other domain checks remain in
their owning editor and service.

Domain components still own row identity, ordering, units, validation,
disabled and read-only states, update callbacks, and empty-domain decisions.
`DataTable` must not infer engineering meaning or change a domain record.

```tsx
import DataTable from "./DataTable";

<DataTable label="Thermal assembly links" className="thermal-input-table">
  <thead>...</thead>
  <tbody>{links.map(link => <tr key={link.id}>...</tr>)}</tbody>
</DataTable>
```

The component accepts normal React table attributes and these additional
properties:

| Property | Required | Default | Meaning |
| --- | --- | --- | --- |
| `label` | yes | none | Accessible table, toolbar, search, viewport, and pagination context |
| `showLabel` | no | `true` | Shows the toolbar title; turn off when an enclosing editor already supplies its title |
| `searchable` | no | `true` | Shows local displayed-value search; use `false` when the owning workflow already filters its source rows |
| `pageSize` | no | `100` | Maximum row groups shown on one page; finite values are rounded down and clamped to at least one |
| `emptyMessage` | no | `No rows to display.` | Message used when the source has no row groups |
| `theme` | no | inherited | Optional `professional-dark`, `light`, `high-contrast`, or `system` palette for this table |

Keep native `caption`, `thead`, and one or more `tbody` elements as children.
The component passes remaining table properties through to the native table.
It composes caller focus and keyboard handlers with its own behavior.

## Themes and custom palettes

By default, tables follow the application's `data-theme` preference from
Settings > Interface: Professional dark, High contrast, or Follow system.
Follow system uses the OS light/dark preference and responds to changes without
remounting a table. Detached result/probe windows read the saved preference and
refresh on same-origin settings storage events. This theme support covers the
shared tables; it does not replace the rest of SPIKE's existing shell styling.

An adapter can set `<DataTable theme="light" ...>` or set
`data-table-theme="light"` on an enclosing panel. A theme attribute establishes
a palette for that subtree. Omit it to inherit the application choice.

All table colors use `--spike-table-*` CSS properties. Define overrides on a
panel or table wrapper to customize a palette without changing engineering
components. For example, start with a dark palette and customize its row bands:

```css
.custom-review-panel {
  --spike-table-surface: #181923;
  --spike-table-stripe: #262838;
  --spike-table-header: #36394f;
}
```

The palette file lists tokens for surfaces, text, borders, editable fields,
dropdowns, actions, focus, locks, errors, and warnings. It also supplies three
authored SVG image tokens (`--table-edit-icon`, `--table-choice-icon`,
`--table-lock-icon`) with matching strokes. Custom palette authors can override
these image tokens too. Keep text at 4.5:1 contrast and essential control/focus
cues at 3:1; retain the pencil, chevron, lock, underline and button shapes so
meaning does not depend on color. Native select menus use the selected palette's
color scheme and option colors. OS forced colors retain native dropdown arrows
and system focus/field boundaries.

## Behavior

Tables start at comfortable density. The Compact button changes density for
that mounted table. Alternating row bands and horizontal separators distinguish
records; a stronger header band separates column titles from data. Direct-entry
text fields have a pencil and an underline. Numeric fields retain their native
spin controls and an underline. Dropdowns have a separate tint and explicit
chevron. Read-only or unavailable fields use a lock and dashed underline;
display-only text has no edit affordance. Actions use distinct buttons, with
removal using the theme's danger palette. An editing guide appears above tables with
controls. These cues supplement native accessibility semantics and keyboard focus.

Search is case-insensitive and requires every entered term
to match a row group's displayed values. Quote an exact phrase, such as
`"Source 1"`, to keep words together instead of matching numbers in other
columns. For form controls it searches the
current value and the selected option label, rather than every option. A custom
renderer can provide `data-search-text` when its visible meaning cannot be
derived from its children or value.

A keyed React fragment is one row group, so a primary row and its expanded
detail row remain together during search and paging. Pagination defaults to
100 row groups. Column headings stay within the local scrolling viewport.
While focus remains inside a row, search keeps that active row mounted; the pin
is released when focus leaves the table.

Keyboard behavior preserves native control semantics:

- Tab and Shift+Tab use native browser focus order.
- Enter and Shift+Enter move to the same editable column in the next or
  previous row when focus is in a single-line input.
- Alt+Arrow moves between editable table cells.
- Arrow keys in controls, Enter in selects, and Enter in textareas retain their
  native behavior.
- Disabled and read-only controls are skipped by table keyboard movement.

The shared interface does not sort or reorder records and does not implement
bulk paste. It makes no performance-timing claim. Domain-specific filtering,
validation, units, and writes remain in the owning workflow.

## Adoption inventory

The active desktop routes production tables through `DataTable`, including
analysis results and probes; terminal and power-tree editors; thermal inputs,
hardware, links, and results; SI/EM tables; external-engine and MCAD review;
assembly topology, materials, board links, connector pairs, and harnesses; net
roles; and the SPICE pin and parasitic grids. `BondManager` keeps its existing
source search and therefore sets `searchable={false}`.

The PI terminal editor keeps its responsive Cards view and offers a Table
button using the same records, pad details, add, pick, and selection actions.
Initial sets of more than six terminals open in Table view. Smaller sets keep
the card layout until the user chooses Table.

Markdown tables in `HelpMarkdown.tsx` and the static help coverage table in
`HelpTopics.tsx` remain document rendering rather than application data grids.
The frozen Python UI, experiments, and the separate SPIKES Studio application
are outside this React interface policy.

## Validation

From `app/`, run:

```powershell
npm.cmd run test:data-table
npm.cmd run test:table-theme
npm.cmd exec tsc -- --noEmit
```

The Node test protects the pure model, rendered controls, search semantics,
grouped-detail paging, and callback identity. Use
`scripts/fixtures/table-interface.html` for browser interaction checks. Verify
search, clear, compact density, page controls, sticky headings, focus pinning,
Tab order, Enter/Shift+Enter, and Alt+Arrow at supported narrow and wide window
sizes. Also confirm that disabled/read-only fields are skipped and native
select, textarea, and arrow-key behavior is unchanged.

When help content changes, regenerate and check its derived artifacts:

```powershell
npm.cmd run help:generate
npm.cmd run test:help
```
