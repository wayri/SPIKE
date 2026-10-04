<!-- SPDX-License-Identifier: Apache-2.0 -->
# Python workspace and EMerge model results

SPIKE shares the corrected Python editor and model-result presentation with
SPIKE-Em. PI, thermal, normal PCB/assembly workflows and extension support remain
available in SPIKE.

## Use the patch antenna

1. Open the Python workspace and select an installed Python interpreter with
   EMerge 3.0.0a19 or a compatible newer runtime. The interpreter is remembered.
2. Open `examples/upstream-emerge/patch-antenna-gui.py` from the source/resource
   root. The native package includes this example and the unchanged upstream
   source pack. Set the workspace root to that source/resource directory.
3. Click **Load model** to mesh the example without running its solver. The model
   opens in the main viewport and the editor floats above it.
4. Click **Run** to solve. The running indicator shows elapsed time and an
   indeterminate progress bar; **Stop** cancels execution. No percentage is
   inferred from solver output.
5. Choose a returned field or radiation dataset in the viewport. Two linked
   plot selectors show returned curves. **Show in viewport** can reopen completed
   output. Closing the result viewer restores the ordinary board viewport.

The floating editor can move, resize or return to centered mode. Output controls
occupy their own row above the logs. Syntax colors remain visible over the
transparent editing layer; pending highlighting and forced colors use readable
plain text. External Python execution preserves the SPIKE workspace/API context;
the built-in debugger remains available on the worker interpreter only.

## Data contract and limits

`spike.plot`, `spike.table`, `spike.spatial` and `spike.mesh` produce bounded
script data views. Failed or nonzero-exit runs cannot admit viewport results.
Both the worker and UI validate finite coordinates, topology and budgets.
Each mesh permits 10,000 vertices and 10,000 triangles, within the aggregate
100,000-cell view budget.

The EMerge bridge records a source/parameter SHA-256 scene ID, per-run UUID,
`emerge-global-xyz` frame and metre units. Physical material regions and fields
overlay only when these match. Copper/PEC and dielectric are distinct materials;
air and unassigned port surfaces are excluded. Original sample coordinates and
values are preserved. Radiation is centered on the captured source origin, but
its radius represents a gain display scale, not observation distance. An
unrelated imported PCB is never assumed to match the antenna's scene.

Material corner triangles are a bounded preview, not a CAD tessellation
qualification. Air-only waveguide walls and oversized previews may be unavailable;
retained full outputs remain separate. EMerge performs meshing and solving.
This integration adds visualization and does not establish convergence or
engineering validation of an example.

## Provenance and verification

The source pack is pinned in `examples/upstream-emerge/manifest.json` to
FennisRobert/EMerge commit `75e6e98170a6628688593f917c1bb63b52578d02`.
Its GPL-2.0-or-later license and notices remain in the separate source directory;
the bridge and capture helper have the same license. SPIKE-owned UI and
script-view contracts are Apache-2.0. No EMerge solver code is incorporated into
SPIKE's numerical core. AI-assisted changes require the same maintainer review
as other changes; numerical validation remains a knowledgeable human task.

Focused checks cover syntax/editing, floating bounds, execution/progress,
interpreter forwarding, failed-result rejection, view admission and matching
geometry, bridge capture and external execution. Production TypeScript/Vite,
architecture/control standards and the PCB parser also pass. A real EMerge
3.0.0a19 patch solve was exercised with the SPIKE-Em production components and
frozen worker; SPIKE's adapted integration has automated checks. Native SPIKE
desktop visual acceptance has not been observed in this session.

A real patch solve also completed through this SPIKE source runtime in 31.156 seconds with 11 admitted views. The required broad Python suite ran 2,559 tests: 16 failures, 25 errors, 72 skips. Representative native-geometry, owned-circuit, MCAD and transient failures were reproduced on untouched HEAD (39 tests: 7 failures, 1 error, 2 skips). Rust host checks compiled and passed 37 tests, with one resident native-circuit test failing because this checkout lacks the qualified circuit payload; one test was ignored. These broad failures remain unresolved and prevent a fully green release qualification.
