<!-- SPDX-License-Identifier: Apache-2.0 -->

# UI map and navigation

This guide describes the current development **Clean** layout. Older installed
releases and **Classic** expose different bars. Both layouts share project data
and solver inputs. The diagram is an authored explanation, not a runtime capture.

![SPIKE Clean UI navigation map: two rows, contextual panels, access routes and study loop](../app/public/help/ui-current/navigation-map.svg)

## The two persistent command rows

1. **Global header:** Menu, Project files, Studies, universal search, Show
   hidden tools, Interface layout, notifications, Help and profile/settings.
   Project files opens new/open/import/save/export actions. Hover an icon for its
   name; Clean uses icons for compact controls.
2. **Document and view row:** a small Workspaces icon, editor tabs and assembly-view tabs share space with
   compact viewport controls. These include 2D/3D, Orbit, Pan, Fit scene, Camera
   view, Selection filter and Viewport tools. Assembly actions appears for a
   multiboard project. Camera controls apply when a viewport is visible; an
   editor can supply its own local tools.

An inspector header, an editor's local tools and the status strip belong to the
opened content. They are not additional global command ribbons. Clean does not
show the legacy ribbon. Its separate floating quick-tools bar starts hidden and
is an explicit preference. Classic provides persistent workspace tabs and the
optional legacy ribbon. See [layout preferences](INTERFACE_LAYOUTS.md).

### Viewport controls and result layers

**2D** and **3D** have visible labels. Separators distinguish view modes,
Orbit/Pan/Fit/camera actions, selection, board translucency and Fields.
The Camera view menu highlights the corresponding cube face for Top, Bottom,
Front, Back, Left, Right and Isometric views.

Hover Camera view, Selection filter, toolbar action menus or **Fields** to
preview options. Leaving both the trigger and popup dismisses a hover preview.
Click a trigger to pin it; pinned menus remain open until an outside click,
Escape, an action or Close. Keyboard opening also pins action menus.

**Fields / Result layers and fields** groups available PI/SI analysis overlays,
EM fields, thermal fields, volume/airflow and Python result views. Choose an
analysis dataset, toggle its visibility, use the supported opacity sliders or
open its existing manager. Missing datasets show **No data**; displaying a
result does not run or validate a solver. Volume quantity, cuts, stream display
and saved-frame playback remain in this same control and main viewport.

**Translucent boards** dims board context while retaining selected trace/net
highlights. It works without a solver result, in single-board and assembly
views. The board-context opacity slider is in Fields; layer visibility and
per-board layer opacity still apply independently. The toggle restores opaque
context without changing the selection or source geometry. Opacity controls
are exposed only where supported by the existing renderer.

### Mechanical objects, dimensions and sections

Mechanical projects add a compact object icon at the viewport's upper-right.
It opens compact **Objects**, **Section** and **Measure** tabs for visibility,
opacity, isolation, cuts and dimensions. Standard plane presets, custom angles,
selection-origin alignment and advanced multi-plane/box cuts share the main
viewport. Dimensions accept assembly-mm coordinates or selected occurrence origins
and draw a line with endpoints. See [mechanical viewport tools](MECHANICAL_VIEWPORT_TOOLS.md)
for the workflow, saved display settings and limits of visual cuts/anchor measurements.

### Studies and panel window actions

In the development UI, the **Studies** button sits in the top toolbar beside
the project selector. At narrower widths it becomes a named icon button.
Its searchable menu opens study management, saved cases/runs, solver modules,
execution setup, and result/EM/volume visualization. These are existing tools;
opening a case or a visualizer does not execute or validate a simulation.

Every managed tool has a **Close (×)** control at its top-right. Right-click
the header, or focus it and press **Shift+F10** / the **Menu** key, to access
the available window actions. Inner project/study manager headers inherit the
same actions. Move to floating window detaches the tool; Dock back returns it.
Panels and editors also offer Expand/Restore; docked side panels support keyboard resizing.

| Action | Effect |
| --- | --- |
| Hide / Minimize | Retains the mounted editor and its inputs; restore it from the hidden-tools menu or its editor tab |
| Close | Calls the tool's existing close workflow and cleanup; unsaved local form inputs may be discarded |
| Move to floating window / Dock back | Transfers the existing panel while preserving its draft |
| Expand / Restore | Expands the current tool or restores the live viewport beside it; does not change simulation data |

Duplicate footer Close buttons are suppressed inside managed panels. Nested
confirmations keep their own controls. If a tool blocks dismissal during an
active operation, its shared Close control and menu action remain disabled.
The compact Studies menu adds no third
toolbar row. These changes require a build containing this development update.


## Keep your place while configuring a task

Setup editors now open beside the existing live board/results viewport by
default. They do not create another board renderer or clear the current
selection. On narrower windows the viewport stays above the editor. **Expand**
is an explicit choice; **Restore** brings the viewport back. The viewport's
navigation controls stay available in the existing toolbar while it is visible.

Panel headers show a compact location trail and four navigation icons:

| Control | In a setup/editor panel | In the Menu popup |
| --- | --- | --- |
| Back / Forward | Revisit previously opened panels, skipping closed tools | Revisit previously browsed menu sections |
| Up | Return to Board & results, the panel's workspace parent | Open the parent menu section |
| Home | Return to Board & results | Return to the root Menu |

After Back returns to the board, Forward remains available beside the editor
tabs. Visiting another tool starts a new navigation branch. Panel history is
local to the current application session, bounded, and separate from project
Undo/Redo. Navigation, Hide and Minimize retain mounted drafts; Close invokes
the existing tool close workflow. Going Back never reverses an engineering
edit or runs a solver. Detached headers use the same workspace panel history.

Gerber import uses **Source -> Stack -> Ports -> Review**. The numbered steps,
current-step description and retained-draft summary explain where you are.
Previous/Next move between sections without clearing inputs or file choices.
Only **Load Gerber study** on Review submits the source. Missing files and
invalid definitions remain explicit errors with the draft retained. The board
visible beside an unsubmitted draft is the current project, not a preview of
new Gerber copper; native mesh preparation and solving remain separate actions.

Gerber setup sections use bounded field columns and compact action buttons. Each
section header has **Help**, which opens its matching offline guide heading.
Closing Help and returning to setup preserves the mounted draft. Substrate bounds
are paired by X and Y so minimum/maximum values can be reviewed together.

## Workspace flyout and persistent layers

The grid icon in the document/view toolbar opens the horizontal workspace
picker. Workspace icons and command groups use compact two-row grids to
expose more controls directly before overflow is needed. Hover to preview it; leaving the icon and its expanded panel hides it.
Click the icon to pin the panel. A pinned panel stays open when the pointer
leaves; click outside, press Escape, or click the icon again to close it.
Click a workspace icon to switch workspaces and show its existing command
inventory. Groups expand in the same panel; Back returns to the previous group.
Disabled commands retain their prerequisites. Arrow keys navigate workspace
icons (Left/Right change columns; Up/Down move between rows); keyboard
opening pins the panel so it remains available without a mouse.
Entering a command group focuses its first available action; Back or Escape
returns focus to the parent action. Closing the picker with Escape returns
focus to its icon.
The expanded panel is temporary and does not add a persistent ribbon row.

The layer control lives on the viewport near the upper-left edge. At rest it
is a small semi-transparent pull icon. Hover or focus reveals the full layer
icon and a responsive grid of layer buttons; clicking also opens it for touch use.
The grid wraps inside the viewport overlay without a horizontal scrolling strip.
Leaving the complete control boundary collapses it to the pull icon. Escape
or moving keyboard focus outside also collapses it. Visibility preferences are
retained. No extra toolbar row or visible scrollbar is added.

The expanded caption names the current board. Selection ownership determines
its layers: a selected board, part or net uses its exact board occurrence.
Selecting another occurrence changes the array and restores that board's
visibility preferences. An object without occurrence ownership in an assembly,
a harness, an MCAD part, or multiple-board selection has no layer-editing
scope and hides the pull. Shared design or net names never establish ownership.
A single-board viewport supplies its active board context.

Layer buttons toggle that board's visibility; **All** restores its layers and
clears a focused-layer view. The settings icon opens opacity and other layer
settings. Arrow controls and keyboard navigation reveal large inventories
without scrollbars. Fixed board tabs and detached board views retain their
own exact occurrence scope; disconnected views are read-only.


### Layer opacity, copper zones and reset

The layer selector uses translucent, sharp surfaces and the local Segoe UI
Variable / Inter / system font stack; it downloads no fonts. **Net names** has
its own prominent downward expansion and shown/hidden indicator.

- **Wheel over a layer:** up adds 5 percentage points of opacity; down subtracts 5,
  bounded to 0–100. The button temporarily shows the number and returns to its
  layer name **one second after the final wheel event**. Its width stays stable.
- **Wheel over All:** adjusts the All master and applies that opacity to every
  layer of the selected board, including currently hidden layers. It preserves
  visibility and every other board's settings. Clicking All still shows layers.
- **Copper-zone icon:** cycles **Filled → Transparent → Outline → Filled**.
  Transparent uses 18% of the chosen layer opacity; outline draws actual outer
  and hole perimeters with no zone fill. Tracks, pads and solver overlays retain
  their own display. These settings never change copper geometry or solver inputs.
- **Reset view:** restores default camera framing/orientation, imported layer
  visibility, 100% layer opacity, and filled zones. It leaves assembly placement,
  results, other boards' layer settings, themes and design/study data intact.

Zone modes and per-board overrides are saved with the project and undo history.
A fixed/scoped board view edits its own occurrence; disconnected views are
read-only. Native KiCad artwork can combine zones, tracks and pads into one
fragment. Alternate zone modes therefore use retained copper geometry while
keeping models/body; Filled retains native artwork where present. Retained
zones are opaque at 100% layer opacity except intentional result/focus dimming.


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


### Net names in the viewport layer selector

Hover the upper-left layer pull for a single selected board, then expand
**Net names** below the layer chips. **Show net names / Hide net names** controls
that board's labels in 2D and 3D. The section expands downward inside the same
control; leaving its full bounds collapses the selector. Selecting multiple
boards hides the selector. Each occurrence retains its own label preference,
including saved projects and occurrence-scoped views.


### Searchable choices and guided setup

Ordinary single-choice dropdowns include search with `*` and `?` wildcards.
Basic PI, geometry and loaded SI, board thermal, PCB EM, native CFD, internal
airflow and assembly CHT forms expose numbered steps with Back/Next and direct
access. See [the setup flow guide](SOLVER_SETUP_FLOWS.md) for the exact domain
sequences, keyboard controls and unchanged execution requirements.

## Search categories and Close behavior

Search results retain their text categories and use matching icon, edge and
badge colors: PI gold, HF/SI cyan, EM violet, thermal orange, solver actions
green, projects/meshing blue, and reports/results pink. Recent-action chips
and searchable option groups use the same presentation. General actions,
view controls, design objects, settings and help retain named categories.
Light and high-contrast palettes adapt these accents; color never indicates
solver readiness or numerical validation.

Recent and Most used switch ordering; an action chip runs its existing command.
Unavailable actions remain disabled. The summary wraps in its own reserved
space rather than overlapping the first search result.

The shared panel Close button invokes the owning editor's original close
control, including unsaved-change confirmation. Hidden setup steps and nested
tools cannot disable their parent panel. An active operation can disable Close
with an explanatory tooltip; an open confirmation must be answered first.
Hide remains available to retain an editor while returning to the viewport.

## Learn with guided pictures

**Help → Home** opens task cards. Choose a task, then use the numbered step buttons or **Back / Next step**. Each step includes the expected result, recovery guidance and an actual UI capture with its control highlighted. Select the picture to enlarge it. **Guided walkthroughs** filters these tasks in Help search; reference pages remain available alongside them.

The [picture walkthroughs](PICTURE_WALKTHROUGHS.md) also cover PI, SI, EM and Thermal setup sequences and distinguish configuration pictures from computed result evidence.

## Context actions and reusable occurrences

### Viewport navigation from the context menu

Right-click anywhere in the main viewport. **Navigate viewport** and **Views**
remain available across all analysis workspaces, including an empty selection.
Search can find these actions directly; for example, `orbit`, `zoom`, or `isometric`.

| Group | Actions |
| --- | --- |
| Navigate viewport | Orbit around clicked point; Orbit/Pan drag mode; Fit all visible objects; Zoom in/out; Reset camera |
| Views | 2D, 3D, Top, Bottom, Front, Back, Left, Right, Isometric |
| Layers and display | Context-specific board layers, copper focus, stackup and component model visibility |

**Orbit around clicked point** captures the original right-click position and
activates Orbit. Visible source or assembly geometry supplies the pivot; empty
space uses the view's reference plane when it can be intersected. Moving the
pointer into the menu does not change that point. Orbit and standard directional
views require 3D; switch using **Views → 3D view** first. In 2D, dragging pans.
The active navigation and dimensional view choices are highlighted and announced.
**Reset camera** restores the default camera and fits the visible scene. The
layer selector's separate reset also restores layer and copper display settings.


### Selection actions and reusable occurrences

Right-click the viewport for actions scoped to the active workspace and clicked
selection. Copper actions belong to the owning board; mechanical selections do
not expose net or circuit commands. Search supports `*` and `?` within this
context. Use **Ctrl+K** to search the full command catalog.

The compact **Edit occurrence** grid provides:

| Action | Effect |
| --- | --- |
| Copy / Ctrl+C | Copy the selected board or mechanical occurrence into the current project clipboard. |
| Cut / Ctrl+X | Copy, then remove the occurrence after dependency checks. |
| Paste instance / Ctrl+V | Create a separately positioned occurrence using retained source geometry. |
| Paste independent board copy | Clone the retained board design under a new design identity. Subsequent design settings are independent. |
| Duplicate / Ctrl+D | Create another instance directly, with a distinct placement frame. |
| Delete / Delete key | Remove the selected occurrence; Ctrl+Z restores the edit. |
| Move / rotate | Open placement controls for the chosen occurrence. |

1. Import a board through the desktop importer so its canonical source is retained,
   or open a project containing retained boards/mechanical objects.
2. Select the occurrence, **Copy**, then **Paste instance** or **Paste independent
   board copy**. The new item is placed apart from existing boards and selected.
3. Use placement controls to move or rotate it independently. Save the project to
   retain the new occurrences. Use **Undo / Redo** to review changes.

Right-clicking copper or a component labels board editing explicitly: it edits
its **entire owning board occurrence**, not the source trace/component. Keyboard
Copy on a source component/copper object copies selection data as text; choose the
board occurrence for geometry duplication. Text fields retain ordinary text editing.
The occurrence clipboard is local to this project/window, is not an arbitrary JSON
import path and does not persist after closing the window.

Imported geometry/model references remain shared for instances; independent board
copies duplicate the retained design data, not the original file on disk. Mechanical
copies retain their model/material references while receiving independent placement
frames. Connections, contacts and solver results are not inferred or copied to new
occurrences. Deletion preserves source files and requires child/relationship review;
explicit board links removed with the occurrence are restored by Undo. The last board
is retained: hide it or create another occurrence first. Active runs and pending
assembly editor drafts block occurrence edits. Native save/reopen acceptance remains
separate from browser interaction and serialized-state tests.

STEP objects need a prepared glTF/GLB visual before Copy, Cut or duplication. Copies
retain that visual source provenance, but exact topology selectors, constraints,
contacts and bonds require preparation for the new occurrence. Deleting an
occurrence also removes its owned package-shape setup; Undo restores both.

## Linked CAD sources

Use **Project manager → Linked CAD sources** to link a retained PCB or mechanical
model to its original local file. Save in KiCad / MCAD, check for changes, review
and apply the exact saved revision. Instance placements remain; affected results
must be regenerated. See the [three-step source-sync guide](LINKED_CAD_SOURCES.md).

## Run and Tutor across workspaces

Use the header **Run** or **Tutor** control to choose a simulation target. The
reserved helper dock keeps the viewport and setup editor usable. It shows the
next actual required item: **Resolve this item → edit and apply → Recheck setup**.
After required inputs pass, review warnings and click **Run simulation**; Run
performs a fresh check before the solver's existing admission path. Tutor adds
Back/Next setup steps without treating navigation as validation.

See [guided simulation runs](GUIDED_SIMULATION_RUN.md) for target coverage,
extension execution boundaries and the distinction between setup readiness and
numerical qualification.


## Floor grid, horizon and origin markers

In **Settings → Interface**, **Orientation grid** controls the 3D procedural floor and subtle false horizon. The floor has no finite rectangular border: grid spacing adapts as the camera zooms and fine lines fade near the horizon to reduce flicker. Graphite, Light and AMOLED backgrounds retain their selected colors away from the grid/horizon.

Disable **Origin axis markers** to hide the colored world-orientation triad. This is independent of the floor grid and of result-axis labels. Use **Apply settings** to retain the preference, including additional board views.

The floor is a display reference, not a simulation mesh, scale claim, physical surface or imported object. It cannot be picked and does not change Fit bounds. Its two-triangle shader uses constant geometry rather than extending a tessellated mesh. Pixel cost still depends on viewport resolution and GPU; no unrestricted frame-rate guarantee is claimed.
