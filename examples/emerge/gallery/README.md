<!-- SPDX-License-Identifier: Apache-2.0 -->
# EMerge project and probe gallery

Open **EMerge example projects** from SPIKE command search, or open a generated
file in `projects/` with **Ctrl+O**. Review source and result warnings. The
[illustrated guide](../../../docs/EMERGE_EXAMPLES.md) explains the 1-2-3 flow,
frequency/field controls, exact probes, exports and advanced EM study families.

`catalog.json` drives the in-app browser; `snapshots/` supplies its inline project
copies, `projects/` holds canonical native packages, and `probes/` records exact
sample recipes. `manifest.json` records actual provenance, hashes and verification.

Regenerate without launching a solver:

```powershell
.venv/Scripts/python.exe -B examples/emerge/gallery/build.py
```

These are first-party packaging and documentation around retained, unvalidated
solver outputs. No new FEM execution is implied. Historical design bindings stay
unchanged and differences from the current importer are disclosed. The ESP32
surrogate retains its existing CERN-OHL-P-2.0 source, attribution and assumptions;
it is not a complete physical ESP32 simulation. See [source notices](../../../THIRD_PARTY_NOTICES.md)
and [original executed dataset descriptions](../gui_workflow/README.md).
