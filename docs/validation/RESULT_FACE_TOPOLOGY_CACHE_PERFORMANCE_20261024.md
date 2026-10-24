# Result face topology cache performance — 2026-10-24

## Scope

The 3D scalar result overlay previously called the full polygon projection,
self-intersection check, and ear-clipping triangulation for every exact face on
every saved-frame update. Saved transient frames retain each layout face's
`vertices_mm` array, so the triangle mapping is topology-bound even though the
scalar sample and value change.

`cachedResultFaceTriangleIndices` now keeps that mapping in a `WeakMap` keyed by
the vertex array. Every lookup compares all coordinates with a retained
`Float64Array` snapshot before reuse, so an in-place topology edit invalidates
the entry. The published index array is frozen once before cache storage, so a
caller cannot corrupt later frames through assignment or deletion. The viewport still rebuilds and disposes its Three.js overlay each
effect; only the CPU triangulation result is reused.

## Bounded benchmark

Command (from `app`):

```text
node scripts/test-result-face-topology-cache.mjs ../output/performance-20261024/result-face-topology-cache/sample-1.json
```

Workload: 2,000 distinct seven-vertex concave faces, 16 playback passes,
32,000 calls. The baseline calls the unchanged uncached
`resultFaceTriangleIndices`; the warm case calls the cache after one population
pass. Both paths produced checksum `1,664,000` over every returned index.

Five separate Node v24.14.0 processes:

| Metric | Baseline | Warm cache |
| --- | ---: | ---: |
| Median | 69.15 ms | 13.17 ms |
| Range | 51.93–71.95 ms | 10.54–31.72 ms |

The final post-review median ratio was 5.25x for this synthetic CPU-only workload. This is not an
end-to-end frame-rate claim: array/color construction, BufferGeometry upload,
materials, renderer work, and scene disposal remain unchanged. Native SPIKE
playback was intentionally not run under the current memory constraint.

## Correctness and checks

- Exact cold and warm triangle arrays are compared for concave, vertical,
  self-crossing, and repeated-vertex faces.
- Every index is asserted, malformed faces preserve an empty mapping, and an
  in-place coordinate edit, vertex replacement, and vertex-count change must
  recompute the same mapping as the uncached reference.
- Index assignment and deletion throw, after which the exact cached baseline
  indices remain unchanged.
- `npm run test:result-performance` passed.
- `npm exec tsc -- --noEmit` passed.

Raw post-review runs are the `final-sample-1.json` through
`final-sample-5.json` files in
`output/performance-20261024/result-face-topology-cache/`.
