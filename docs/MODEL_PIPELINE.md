# Offline 3D Model Pipeline

The browser renderer uses WebGL and Three.js, but it does not load STEP files directly. The model pipeline therefore has explicit states:

- `ready`: bundled `.gltf` or `.glb` asset.
- `conversion_required`: local STEP/STP asset found, awaiting conversion.
- `missing`: KiCad references a model that cannot be resolved locally.
- `proxy`: no model reference; render a procedural package proxy.
- `unsupported`: another model format requires an importer.

SPIKE never presents a proxy as the original manufacturer model. The result and UI should show the state so users know whether the 3D view is exact, converted, or approximate.

The e-brake fixture currently provides 115 model references. The current machine does not resolve those KiCad library references through the configured environment variables, so they correctly appear as `missing` rather than being silently omitted.

Future conversion options, in order of preference:

1. A bundled offline converter in the packaging toolchain.
2. A user-selected FreeCAD/Blender/Assimp conversion tool during import.
3. Procedural proxies when conversion is unavailable.

The desktop runtime remains offline. Conversion happens during import or packaging and never requires a network service.

## Global Library

The local worker exposes `model_library` using the
`spike/model-library/v1` contract. It searches:

- an optional `SPIKE_MODEL_LIBRARY` path list;
- installed KiCad 8, 9, and 10 model roots;
- the per-user SPIKE model folder;
- one directory explicitly selected by the user.

Search accepts a text query and a bounded result limit. Unreadable directories
are skipped. No model is executed, no remote texture is loaded, and no network
fallback is attempted. Component-to-model assignments are saved in
`design.model_assignments` in the SPIKE project package.

Assignment does not imply browser readiness. STEP/STP and WRL/VRML sources retain
their source path and provenance until a local converter creates a checked GLB
cache artifact. The assignment UI must continue to show missing and conversion
states rather than mixing procedural proxies with authoritative models.

Inspect the current machine's offline conversion capability with:

```powershell
python -m python.spike_cli model-tools
```
