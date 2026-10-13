# PALACE and Xyce native solver workbenches

These optional applications provide dedicated desktop controls and native output
inspection. They are experimental. Install each runtime separately from its
upstream project; SPIKE does not bundle it. An enabled extension, visible plot or
successful adapter test does not establish numerical validation.

## Open a workbench

1. Open Extensions and enable/trust the PALACE or Xyce extension.
2. Select the engine in its registered EM, PI or HF/SI workspace route, then open
   its configuration panel. Native inputs can be authored without a loaded board.
3. Enter the installed executable path or use runtime discovery. Missing engines
   produce a recoverable diagnostic rather than a synthetic result.

## PALACE

Import a native JSON configuration, or edit its Problem, Model, Domains,
Boundaries and Solver sections. Select Driven, Eigenmode, Transient,
Electrostatic, Magnetostatic or BoundaryMode. Supply an absolute local mesh path,
positive native Model.L0 length scale, materials, boundary attributes and ports.
The application does not infer these from a PCB or assembly.

Validate the input, review the mesh digest, prepare a private job, then run with
bounded time, memory and serial resources. Native validation is distinct from
local admission checks when the engine is unavailable. Import retained job output
for native CSV tables, diagnostics and artifact hashes. Optional VTK support shows
bounded exact-node samples from supported VTU point fields; it is a sampled preview,
not a full surface/volume renderer or board overlay. Inspect units and mesh scale.

## Xyce

Import or edit a titled netlist, supply text libraries using safe relative include
names, and request CSV output using `.PRINT ... FORMAT=CSV`. Preflight checks the
supported subset. Prepare retains an integrity-bound private case; Validate uses
native syntax checking; Run returns native diagnostics and finite CSV waveforms.
Inspect revisits a retained case. Cancel uses the owned worker lifecycle.

The adapter intentionally rejects arbitrary options, plugins and outside file
references. See the extension README for supported statements and platform gates.
Windows uses Job containment. Source Linux uses a parent-death guardian; macOS
and frozen Linux execution are gated pending equivalent containment.

## Projects and results

Settings and returned native results are saved in `.spike` analysis extension
workflows and restored directly in the workbench. Save copy without results keeps
configuration and strips saved native output. Large raw solver artifacts stay in
private local jobs and are referenced by hashes; project persistence does not
embed every native output file or make runtime paths portable to another machine.
These outputs remain separate from canonical SPIKE board analysis fields.

## Evidence and limits

Focused adapter, UI, project-state and architecture checks cover missing runtimes,
invalid inputs, containment helpers, finite output admission and rendering states.
No live PALACE or Xyce accuracy comparison was run here because neither runtime
was available. No automatic circuit/field coupling, MPI execution or GPU support
is claimed. Native solver accuracy and packaged execution need independent checks
before a release claims those capabilities.

- [PALACE adapter details](../extensions/palace_suite/README.md)
- [Xyce adapter details](../extensions/xyce_suite/README.md)
