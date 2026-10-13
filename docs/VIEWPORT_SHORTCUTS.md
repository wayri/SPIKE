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
