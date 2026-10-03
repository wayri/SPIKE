# Workbench interface segments

`app/src/CommandStrip.tsx` owns horizontal command overflow and keyboard access.
`CommandStrip.css` owns its scroll affordances. `WorkbenchChrome.css` owns the
main window's title, menus, ribbon, viewport bars, dock tabs, and density tokens.
Keep workflow state and command callbacks with the existing owning component.

## Reusing a command row

```tsx
<CommandStrip label="Viewport" className="canvas-toolbar">
  <button onClick={fitScene}>Fit</button>
  <select aria-label="Camera view">...</select>
</CommandStrip>
```

Use a descriptive `label` for the scroll controls and focusable command region.
An optional `trailing` slot keeps essential controls outside the scroll area;
the ribbon's Minimize/Expand control uses it. `as="nav"` supplies navigation
semantics. `id` can connect an existing disclosure button through aria-controls.
Give icon commands accessible names and keep related buttons in a group. Native
selects keep their normal arrow-key behavior. Floating custom menus must live
outside a scroller (for example in a portal); do not put absolute popovers in it.

Arrow buttons, the thin scrollbar, and Arrow Left/Right or Home/End on the command
region reach overflow. Tabbing to a hidden command reveals it without remounting
the controls. ResizeObserver tracks both the available width and group widths.
No commands disappear because their priority is low on a small screen.

## Density and layout

The main window uses a 38px title row, 32px tabs and 66px ribbon at wide sizes.
At widths up to 1400 CSS pixels or heights up to 820 pixels these reduce to
34px, 30px and 58px. Buttons retain readable labels and generally 26-28px targets;
scroll buttons and short-window contextual controls have 24px minimum targets.
The OS window frame remains managed by the operating system.

`--ui-title-height`, `--ui-tabs-height`, `--ui-ribbon-height`,
`--ui-dock-tabs-height`, `--ui-status-height`, `--ui-control-height`, and
`--ui-command-gap` are the shell density extension points. Viewport command and
context rows use `--ui-canvas-toolbar-height` (32px) and
`--ui-context-toolbar-height` (28px). The assembly selector uses 26px controls in
a 31px row. `--ui-viewport-footer-height` reserves a 30px footer for existing setup and
status controls. The independent notification-dock migration is outside this
UI engine change; existing notification and inspector behavior is preserved.
The workspace-only summary is a single 28px line. Analysis summaries have a
44px minimum and horizontal scrolling for long labels and actions. Dock tabs
are 28px and the status row is 24px. Compact padding preserves text sizes,
focus indicators and clickable controls.

Palette values inherit the
shared table theme tokens, including high contrast and system preferences.
Individual analysis panels and the board scene retain their existing palettes.

The bottom dock uses at most 26% of the window height, or 20% below 700px. Its
contents remain available when opened at short sizes. The resize handle follows
the actual track height. Side widths are bounded relative to the window, and
manually reopened panels retain their space. Existing automatic initial dock
collapse at 1180/920px remains. Internal scrollbars remain visible for discovery.
Compact viewport and dock command rows use overflow arrows and keyboard
scrolling without allocating another row for a scrollbar. The canvas command
row also adapts to its available width through a container
query, including when other docked tools are open. Menus wrap and their dropdown
contents scroll; they remain outside the command scrollers.

## Reproducible checks

Run `npm run test:command-strip`, the workspace/resize/context checks, and build.
The focused test exercises overflow edges, resize recovery, focus reveal, native
select keyboard behavior, and observer cleanup. Open
`/scripts/fixtures/command-strip.html` through Vite for long labels, 320/420/720/1100px
panels, disabled/recovered Focus, and the shared palette variants. This fixture
contains no board or numerical results and does not establish solver validity.

For runtime visual acceptance, check the actual desktop at 1440x920, 1366x768,
1280x720, and the supported minimum 900x620. Check effective CSS viewport size
because display scaling/browser zoom can change it. Include long project names,
open inspectors, a selected object with a model notice, both ribbon states,
expanded Console/Probe docks, and Mesh/Solve. Reach the final toolbar command by
scrolling and keyboard; verify menu dropdowns separately. Native visual checks
must be reported as unverified if UI interaction is interrupted.
