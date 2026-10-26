# Result overlay color scratch — 2026-10-25

## Change

The 3D scalar overlay now creates one `THREE.Color` inside the existing
`scalarSamples.length` effect branch and reuses it at the four audited color
write sites: via geometry, exact face vertices, contour-grid vertices, and
fallback instances. Geometry, sample mapping, materials, visibility,
generation, and disposal are unchanged.

Each consumer copies the color immediately. Numeric arrays receive `r`, `g`,
and `b` values, while the installed Three.js `InstancedMesh.setColorAt` writes
the components into its `Float32Array` with `color.toArray(...)`.

## Bounded check

Command from `app`:

```text
node scripts/test-result-color-scratch.mjs ../output/performance-20261025/result-color-scratch/benchmark.json
```

The check performs 4,000 writes through each implementation, for 8,000 total
color writes. It compares all 12,000 Float32 output components with `Object.is`
and includes negative zero, values below and above the admitted ratio, both
infinities, and NaN to preserve Three.js behavior exactly. It also mutates the
scratch color after `InstancedMesh.setColorAt` and verifies the previously
written instance remains unchanged.

| Metric | Per-write allocation | Scratch reuse |
| --- | ---: | ---: |
| `THREE.Color` constructions | 4,000 | 1 |
| CPU time, single bounded run | 2.0671 ms | 0.3979 ms |

The observed CPU ratio was 5.20x in this small synthetic run. It is not a
viewport frame-rate claim. Actual playback still rebuilds result geometry and
uploads buffers; this change removes only transient Color construction.

Full TypeScript, application build, and native playback were intentionally not
run because the machine had about 1.1 GB free RAM and 214 MB free disk.
