<!-- SPDX-License-Identifier: Apache-2.0 -->

# UI map and navigation

This guide describes the current development **Clean** layout. Older installed
releases and **Classic** expose different bars. Both layouts share project data
and solver inputs. The diagram is an authored explanation, not a runtime capture.

![SPIKE Clean UI navigation map: two rows, contextual panels, access routes and study loop](../app/public/help/ui-current/navigation-map.svg)

## The two persistent command rows

1. **Global header:** Menu, Project files, universal search, Workspaces, Show
   hidden tools, Interface layout, notifications, Help and profile/settings.
   Project files opens new/open/import/save/export actions. Hover an icon for its
   name; Clean uses icons for the workspace and layout selectors.
2. **Document and view row:** editor tabs and assembly-view tabs share space with
   compact viewport controls. These include 2D/3D, Orbit, Pan, Fit scene, Camera
   view, Selection filter and Viewport tools. Assembly actions appears for a
   multiboard project. Camera controls apply when a viewport is visible; an
   editor can supply its own local tools.

An inspector header, an editor's local tools and the status strip belong to the
opened content. They are not additional global command ribbons. Clean does not
show the legacy ribbon. Its separate floating quick-tools bar starts hidden and
is an explicit preference. Classic provides persistent workspace tabs and the
optional legacy ribbon. See [layout preferences](INTERFACE_LAYOUTS.md).

## How deep do menus go?

Count each selected item **after opening Menu**, including the final action.
Two persistent rows describe screen organization; they are not a two-click
limit on the command tree.

| Route in the current command tree | Choices after Menu | Faster access |
| --- | --- | --- |
| Project → New project | 2 | Project files → New project, or Ctrl+N |
| Analyze → Power integrity → DC PI setup | 3 | Ctrl+K → DC PI setup |
| Design & view → Viewport tools → Navigate → Orientation grid | 4 | Ctrl+K → Show orientation grid |
| Analyze → Workspaces → Home → PROJECT → Save | 5 | Ctrl+S or Project files → Save |

These are actual representative paths, not a promise of a fixed maximum for
every state or extension. Workspace groups reuse the existing tool inventory;
specialist routes can therefore be deeper than the main section/group/action
pattern. **All actions** lists leaf actions with their paths. The Menu's own
search matches labels and paths across groups. **Back** or **Escape** goes up
one level; at the root Escape closes Menu. Use the close control to dismiss it.

The icon popovers for camera presets, selection filters and adding views expose
choices directly. A chevron in Menu denotes another group; a check mark denotes
a selected choice or enabled toggle. Disabled items remain subject to project,
selection, runtime and solver prerequisites.

## Sections and workspaces

The six Menu sections organize commands by intent. A workspace changes the
active workflow; an editor tab changes the open document; a panel shows focused
controls without replacing that document.

| Menu section | What belongs here |
| --- | --- |
| Project | New/open/import/save/export, editing history, project management, assembly/connectivity and application settings |
| Design & view | Board display, layer/flex managers, camera and selection, navigator/inspector and workspace panels |
| Analyze | PI setup, simulation workspace entrypoints and workspace tool groups |
| Results & reports | Result display controls, probe export, screenshots and engineering reports |
| Tools | Engineering review, automation/Python, diagnostics, extensions, open panels and window restoration |
| Help | Guides, validation tools, updates, bug reporting and About |

| Workspace family | Main task |
| --- | --- |
| Home | Import, inspect and review design readiness |
| Mesh / Solve | Shared preparation and execution stages for the active supported analysis |
| PI / HF / SI | Electrical setup, power paths, ports, channels and domain-specific results |
| EM / Thermal | Domain setup and supported field, heat or flow routes; CFD/CHT entrypoints depend on the chosen route |
| Probes / Results / Reports | Examine returned quantities, compare records and export evidence |
| Extensions / Settings | Manage additional tools, runtimes, resources and interface preferences |

**Solver manager** is the inventory of named blocks, dependencies, runtime
readiness and supported setup routes. Find it through Ctrl+K or
Menu → Design & view → Workspace panels. Its categories describe modules;
they do not replace the workspace workflow or establish numerical qualification.

## Three ways to navigate

- **Task first:** Ctrl+K, then type the action, part reference, net, solver name
  or a supported sentence. Review the selected board/occurrence and target.
  Missing supply, load, return, boundary or material inputs must be supplied in
  setup; ambiguous matches need resolution. Sentence support is route-specific.
- **Domain first:** open the workspace icon, choose the domain, then open the
  contextual setup/tool. Use Mesh and Solve when the workflow directs you there.
- **Object first:** choose a selection filter, pick a board/part/net and inspect
  its identity and properties. Use the nearby contextual tools or right-click
  menu for actions relevant to that selection.

Universal search also indexes live rendered controls. Some conditional fields
become discoverable only after their owning editor is open; external engine
windows have their own controls. See [search coverage and limits](COMMAND_ACCESS.md).

## Tabs, panels and recovery

Power tree, circuit and other supported document editors open as tabs. Assembly
tabs select the main scene or an occurrence-scoped view. The Add assembly view
icon creates another view; it does not create a new physical board. Switching
tabs preserves supported drafts, but is not a project save.

Panel headers provide scale, expand/restore, hide and supported detach controls.
Resize with the dock grip. Hiding preserves current inputs; use **Show hidden
tools** or search the opening command to restore the tool. A close action can
have editor-specific semantics; save before closing or reloading. Native
detachment requires the desktop shell.

## A complete study, from start to finish

**Import → review identity/units/materials → setup → mesh/preflight → solve →
inspect results → save/report.**

For PI, for example: import the board; choose the exact board occurrence, net,
source/load pads and return; enter physical values; review mesh and preflight;
run; check warnings, units, balance and convergence; then save the `.spike`
project and export the desired evidence. Missing inputs return you to setup.
Other domains use the same broad loop with their own required boundaries and
validity limits. See the [UI quick start](UI_QUICKSTART.md),
[analysis gallery](ANALYSIS_GALLERY.md) and [solver status](SOLVER_STATUS.md).

## Maintenance scope

The map follows `App.tsx`'s `focusCommands` / `focusCommandInventory`,
`ribbonContentFor`, `FocusCommandPanel.tsx`, `ViewportEssentialTools.tsx` and
`WorkspaceViewTabs.tsx`. Update this guide and its shared offline SVG when those
routes change. The README and Help intentionally use the same diagram.
