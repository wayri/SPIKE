# Component maker and reusable libraries

Open **Component maker…** from the Libraries menu or command search. Importing
or opening a package never executes its code.

## Make a part

1. Set a stable ID, name, version and licence description.
2. In **Symbol & pins**, edit the body, add labeled pins, drag pins and draw
   lines, rectangles or circles. Pin IDs are stable connection identities.
3. In **Model / code**, choose SPICE, C++ or Verilog. Enter source and entry name,
   and record assumptions/provenance. No JSON editing is required.
4. Validate, save a `.spkcmp` package or add it to the searchable user library.
   Changing an installed ID/version requires a new version or fork.
5. For a build, review the code, approve the current behavior and choose an
   output directory. Reports show the tool, result, artifact and limitations.
   Changing the implementation changes its approval digest.

Unsaved drafts prompt before replacement or closing, including closing Studio.
Pending pin-field edits are committed by validation/save. Library searches use
an in-memory index; **Reload user library** refreshes changes made elsewhere.
Choose **Component → Configure compiler / HDL tools…** to select installed
compiler executables. These settings do not approve or run model code.

Open `examples/components/rc_lowpass.spkcmp` for a working three-pin RC example
with an explicit reference terminal. Validation/build output has its own tab.

The versioned package is data-only JSON internally. Unsupported imported source
can be retained; placement and build reject unsupported constructs explicitly.
It is not a universal semiconductor interpreter or arbitrary DLL loader.

## Execution paths

| Language | Build | Place / attach |
| --- | --- | --- |
| SPICE | Parser preflight and source artifact; no numerical qualification | Explicit pin-to-net mapping, then one undoable insertion |
| C++ | Existing sampled `control_step` ABI using the configured compiler | Loads the controller editor, clears trust and requires binding review |
| Verilog | Icarus `.vvp` compilation when installed; no automatic execution | Loads the HDL editor; no analog pin co-simulation implied |

SPICE `.MODEL` imports need a supported primitive prefix and terminal order.
Recognized diode/BJT/MOSFET cards supply conventional defaults; other families
need explicit choices. `.SUBCKT` pin order must match the symbol. Dependencies
must be self-contained: includes, library files, top-level testbenches and
simulation commands are not portable component definitions.

Inserted subcircuits display as compact reusable symbols with labeled public
pins while their native flattened components remain authoritative for solving.
Double-click enters the real hierarchy; parent navigation returns to the block.
Blocks support selection, movement/dragging, rotation, fit, persistence and undo.
Single primitive models retain custom geometry. Literal node `0` remains
global ground, regardless of public pin mapping. Model-name conflicts stop
insertion; no unsafe automatic renaming occurs.

Ambiguous or stale source/pin/package mappings reveal the native flattened
circuit with a diagnostic, never guessed connections. Public ports with no
native terminal are visibly non-wireable. Proxy clipboard duplication and
mirroring are currently rejected explicitly; insert another instance through
the library/maker instead. Each insertion has independent scoped internals.

C++ here is a **sampled controller**, not a continuous residual/charge device
SDK. Verilog compilation is not synthesis, timing qualification or mixed-signal
coupling. Bounded compiler workers are not an OS-enforced hostile-code sandbox.
The existing HDL editor can run digital testbenches with Icarus/VVP and display
their timing data. Compilers remain separately installed tools, not bundled
dependencies.

The installed executable supports `--component-self-test <report.json>` for
the fixed application-owned RC, sampled C++ and digital Verilog/VVP workflows.
It writes tool/native hashes and actual results. Missing tools are explicit
skips and cause this acceptance check to fail; import never invokes the check.

## Capture an existing circuit

Select parts, right-click and choose **Components / compile circuit → Make
component from selected circuit…**. Inside a subsheet, choose **Make reusable
component from this subsheet…**. A maker opens with generated SPICE, public pins
and capture provenance. The original circuit is unchanged.

Selection capture exposes crossing nets (and ground where necessary), retains
required definitions and rejects missing current-control dependencies. Subsheet
capture specializes supported instance parameters. Nested/scoped contexts whose
semantics cannot safely be retained are rejected, not guessed. Apply pending
circuit-text edits before capture.

Capture is equivalent source packaging, not order reduction, manufacturer
qualification or a compiled black-box physics model. Test the new component
before reuse. Software checks include pin identity, save/reopen, undo, native RC
capture equivalence, parameter-shadowing rejection, actual compiler invocations,
exact consent digests and native wx workflows; these do not qualify user physics.
