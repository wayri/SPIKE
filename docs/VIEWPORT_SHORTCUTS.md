# Viewport shortcuts

The shortcut manager opens with **Ctrl+F1**, or from Settings / Keyboard shortcuts
and universal search (**Ctrl+K**). It lists all configurable actions and fixed
application keys. Search by command, group or key; select a binding and press its
new chord. Delete clears it. A conflicting assignment offers an explicit swap.
Reserved project, clipboard, menu and host keys cannot be overwritten.

## Presets and compatibility

New installations use the KiCad-style preset. Core view directions, model-category
keys, pivot and zoom follow the available actions in the
[official KiCad action reference](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#actions-reference).
SPIKE adds its own analysis, probing, assembly and result controls.
The legacy SPIKE preset remains available. Existing saved custom bindings are
preserved. A newly added default that conflicts with a saved key becomes unassigned
rather than replacing the user's command; assign it in the manager.

This is an action mapping, not a claim that SPIKE implements every KiCad editor
operation. Home fits the current scene. Pivot requires 3D. Cursor controls use
actual viewport pointer geometry; unavailable points are reported and zoom falls
back to the view center. Fast pans use Shift+Arrow; Ctrl+Arrow steps saved frames.

## Scope and data

Typing, text editors, menus and modal dialogs retain keyboard ownership. Modifier
chords support Ctrl (or Cmd), Shift and Alt. Held pan/zoom keys can repeat; held
toggle and setup keys do not repeatedly launch windows or flicker visibility.

Probe and context-menu keys use the existing object picking at the viewport
cursor, with the current selection as a fallback. Net highlighting does not make
an electrical connection between equal names on separate boards. Layer navigation
acts on the focused occurrence in assemblies. In a single-board view it isolates
the chosen layer; Show all layers restores the display.

Analysis shortcuts open setup workflows; they do not bypass solver admission or
execute a solve automatically. Playback and frame stepping require saved transient
frames. Field visibility toggles use the active analysis domain. Cancel simulation
operates only on an active cancellable worker. Explode is a presentation transform
and leaves retained physical board placements unchanged.

## Default bindings

| Group | Action | Shortcut |
| --- | --- | --- |
| Viewport | Fit board / home view | Home |
| Viewport | Zoom in at cursor | F1 |
| Viewport | Zoom out at cursor | F2 |
| Viewport | Pan mode | P |
| Viewport | Orbit mode | O |
| Viewport | Pan left | ArrowLeft |
| Viewport | Pan right | ArrowRight |
| Viewport | Pan up | ArrowUp |
| Viewport | Pan down | ArrowDown |
| Viewport | Pan left faster | Shift+ArrowLeft |
| Viewport | Pan right faster | Shift+ArrowRight |
| Viewport | Pan up faster | Shift+ArrowUp |
| Viewport | Pan down faster | Shift+ArrowDown |
| Viewport | Focus selected object | Ctrl+F5 |
| Viewport | Center view at cursor | F4 |
| Visibility | Next copper layer | PageDown |
| Visibility | Previous copper layer | PageUp |
| Visibility | Show focused copper layer | Ctrl+Shift+J |
| Visibility | Show all layers | Ctrl+Shift+O |
| Views | Top view | Z |
| Views | Bottom view | Shift+Z |
| Views | Front view | Y |
| Views | Back view | Shift+Y |
| Views | Left view | Shift+X |
| Views | Right view | X |
| Views | Isometric view | I |
| Views | Flip board view | F |
| Views | Set rotation pivot at cursor | Space |
| Views | Toggle 2D / 3D | V |
| Visibility | Show / hide 3D models | M |
| Visibility | Show / hide surface mount models | S |
| Visibility | Show / hide through hole models | T |
| Visibility | Show / hide axes | Shift+A |
| Visibility | Show / hide vias | Shift+V |
| Visibility | Show / hide net names | Shift+N |
| Selection and nets | Highlight selected net | &#96; |
| Selection and nets | Toggle net highlighting | Ctrl+&#96; |
| Selection and nets | Clear net highlighting | Shift+&#96; |
| Selection and nets | Isolate selected net | Shift+H |
| Selection and nets | Select all object types | Shift+1 |
| Selection and nets | Select components only | Shift+2 |
| Selection and nets | Select nets only | Shift+3 |
| Selection and nets | Add probe at cursor | Shift+P |
| Selection and nets | Show actions at cursor | Shift+F10 |
| Workspace | Show / hide command ribbon | R |
| Workspace | Show / hide layer manager | L |
| Workspace | Show / hide design navigator | N |
| Workspace | Show / hide analysis panel | A |
| Workspace | Show / hide results dock | D |
| Workspace | Open schematic viewer | Ctrl+Shift+H |
| Analysis | Open shared Mesh workspace | Ctrl+Shift+M |
| Analysis | Open shared Solve workspace | Ctrl+Shift+U |
| Analysis | Open power integrity setup | Ctrl+Shift+P |
| Analysis | Open signal integrity setup | Ctrl+Shift+I |
| Analysis | Open thermal setup | Ctrl+Shift+T |
| Analysis | Open electromagnetic setup | Ctrl+Shift+E |
| Analysis | Open SPICE workbench | Ctrl+Shift+B |
| Analysis | Open study workspaces | Ctrl+Shift+D |
| Results | Show / hide result overlay | Ctrl+Shift+R |
| Results | Play / pause transient results | Ctrl+Space |
| Results | Previous result frame | Ctrl+ArrowLeft |
| Results | Next result frame | Ctrl+ArrowRight |
| Results | First result frame | Ctrl+Home |
| Results | Last result frame | Ctrl+End |
| Results | Open result plots | Ctrl+Shift+L |
| Results | Show / hide trace values | Ctrl+Shift+V |
| Assembly | Open assembly workspace | Ctrl+Shift+A |
| Assembly | Toggle exploded assembly | Ctrl+Shift+X |
| Assembly | Open harness manager | Ctrl+Shift+W |
| Assembly | Open thermal contacts | Ctrl+Shift+Q |
| Analysis | Cancel active simulation | Shift+Escape |
| Selection and nets | Open probe table | Ctrl+Shift+F |
| Application | Shortcut manager | Ctrl+F1 |

Run `npm run test:shortcuts` from `app` for catalog, manager, camera and dispatch checks.

## Mouse navigation

The Navigate menu uses distinct orbit, hand, direction, grid and keyboard icons.
Orbit mode uses left drag to rotate in 3D. Hold **Shift + left drag** to pan
temporarily; the next unmodified drag orbits again. Pan mode pans with or without
Shift. 2D views pan with left drag and do not orbit. Middle/right drag pan; the
wheel zooms. Shift + wheel retains the existing net-current tuning behavior.
The gesture modifier is read at drag start; release the drag before changing modes.

## Viewport background and orientation

Navigate → Orientation grid toggles a faint ground grid independently of Coordinate axes. The grid extends beyond single-board and assembly bounds and is available with an empty scene. Navigate → AMOLED · true black selects an exact black viewport background; turn the grid off for an uninterrupted black background. Both preferences persist between sessions and are also available in Settings → Interface. Board, selection, result colors and the application theme retain their separate controls.

## Search sentences and commands

Open Search or press Ctrl+K. Type a command, use Up/Down to choose its exact target, Tab to complete the sentence, and Enter to execute. Examples:

- `run PI on net netK-A1`
- `configure PI for net /Power/VCC`
- `focus part R1`
- `highlight net GND`
- `isolate net GND`
- `show layer F.Cu` or `hide layer B.Cu`
- `please open thermal` or `could you open the settings`

Search suggests names from the loaded board; partial names and quoted names with spaces are supported. Unknown names do not fall back to another net. In an assembly, focus an occurrence of the active design first; commands remain scoped to it. PI uses internal DC analysis and its existing preflight. A configured net can run with its existing sources and loads. A different net opens setup with cleared terminals and return-path assignments for review. Search does not invent electrical boundary conditions, parse arbitrary solver parameters, or execute shell code. Selected extension engines continue through their own setup controls.

## Floating panels and scale

Drag a tool panel or Menu header beyond the main window and release to open it
in its own native window. The Detach button provides the same action without a
drag. Each floating panel has its own taskbar entry and ordinary native resize,
minimize and maximize controls. Dock back or close the native window to return
the same panel and its current inputs to the workspace. Closing SPIKE closes
its floating panels; save your project before exiting.

The percentage selector changes only that panel content. Settings > Interface >
UI scale changes the application and its first-party windows from 65% to 150%.
Narrow result panels stack controls instead of clipping them. Browser previews
need popup permission. A failed detach leaves the draft docked and shows an error.

Floating panels use a linked blank document and retain the main React state;
they do not gain file or solver permissions. Analysis Guide target highlighting
requires docking the guide beside the workspace.

## Render quality and frame budget

Settings > Interface render quality preserves higher pixel density in Balanced
and Quality modes; Performance reduces resolution for dense scenes. The maximum
FPS preference now caps moving frames with a phase-preserving schedule, avoiding
alternate-frame drops caused by early display timestamps. Stationary views use
5 FPS and camera damping follows elapsed time.

Returned current/field vectors use two instanced geometry batches rather than
one draw object per arrow. Shadows refresh on scene changes and throttled
camera-light updates rather than rebuilding every rendered frame. These changes
reduce rendering work without altering solver samples. They do not establish a
measured GPU speedup or guarantee a frame rate on every device.

## PI endpoint sentences and missing details

With a board loaded, search can prepare `on board run PI on netx from C10 to U21`.
It also accepts multiple endpoints, for example `run PI from C10 and J1 to U21
and U22`. Add `Vsup=3.3V Isup=2A Isink=250mA` for an explicit single-source,
single-sink example. Spelling suggestions are bounded lexical matches, not an
unrestricted language interpreter. Fuzzy component identities remain unresolved
until selected. A net is inferred only when every exact endpoint shares one
unique rail; multiple shared rails require a choice. Assembly commands remain
scoped to a focused occurrence of the active board.

The PI setup assistant asks for missing voltage, source capacity, sink allocation
and return treatment. Isup means an optional source capacity, not a prescribed
source operating current. An unlimited ideal source is an explicit choice.
Multiple supplies require individual voltages/capacities; a total Isink across
multiple sinks requires per-component allocations. Edited totals differing from
the sentence require acknowledgement. A capacitor reference identifies a supply
location; it does not create a DC source from the capacitor itself.

Only copper pads on the selected rail are proposed for each IC. Equal sharing
is a visible editable assumption. Enable/exclude pads or choose custom weights;
all allocated pad currents add to the supplied component total. A pad on another
rail or ground is excluded. Selecting the net cannot establish IC internal pin
functions, package current sharing, sequencing or per-domain consumption.

Apply each component allocation, then review PI setup or run through the existing
worker/preflight route. Editing a draft invalidates its applied allocation. An
explicit return requires setup of its copper terminals before running. Changing
the board or occurrence invalidates the assistant. Generated sources and per-pad
loads use the existing persistent PI terminal records. Their currents remain
editable under Current sinks in cards/table; the component-sharing editor is also
available there for existing setups and batch nets. Redistributing loads clears
explicit load-return pairs so they can be reviewed again.


## Reviewed requests across SPIKE

Ctrl+K can prepare SI, thermal, electrothermal/hybrid, EM/RF, CFD/CHT reference,
import, assembly, meshing, model assignment, study, retained-result and export
requests. This is bounded lexical planning with typo suggestions, exact object
binding and dimensioned values, rather than an unrestricted language model.
Examples:

- `run SI on net TX return GND fstart=0Hz fstop=1GHz impedance=75ohm`
- `run thermal on U1 power=2W ambient=30C duration=60s`
- `run electrothermal ambient=25C duration=2s`
- `run EM on net TX return GND fstart=1MHz fstop=1GHz`
- `import touchstone`, `import step`, `open assembly`, `move board Main`
- `mesh board meshsize=0.5mm`, `open studies`, `export step`

Select the suggested request to review exact objects, ambiguities and missing
values. Applying it prepares the existing editor; it does not start a solver.
Frequency bounds and ambient temperature are requested where needed. Multiple
component heat inputs must add to the supplied total. Object identity is scoped
to the focused board occurrence; different occurrences with equal names are not
connected. Changed geometry/project context invalidates a draft.

Built-in SI receives canonical signal/reference IDs, frequency bounds and
reference impedance. A rise time or component reference remains pending explicit
waveform/pin review. SI geometry requires a DC start at 0 Hz. Thermal receives
heat, ambient and duration while retaining material/contact and board thermal
resistance data. Previous results are invalidated. Studio feedback receives
ambient in Kelvin (Celsius plus 273.15) and supplied duration, retaining model
bindings but requiring renewed review. Board EM receives selected/return net
names and sweep bounds; these do not establish spatial ports.

Selected extensions retain their own editors: the request summary explicitly
marks values awaiting manual transfer. Assembly thermal/EM requests open their
retained-geometry editors with the supplied inputs pending explicit solid/port
mapping. Mesh requests preserve selected extension routes. File imports and
exports retain their normal file/destination pickers and validation.

General board/assembly CFD and CHT remain unsupported. Explicit native CFD and
SU2 CHT cavity/reference requests only open their declared benchmark workflows.
An assembly RF extraction request is not replaced by a single-board channel.
No new solver validity or multiphysics capability is established by search.
