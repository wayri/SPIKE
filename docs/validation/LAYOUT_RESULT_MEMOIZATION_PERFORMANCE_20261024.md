# Layout result memoization performance - 24 October 2026

## Scope

The 2D result viewport filters, geometry-checks, spatially thins, and ranges
dense scalar and vector samples. Both memoized pipelines previously depended on
the complete `ResultVisualization` object even though they read only
`visibleResultLayers`. Playback frame controls, fusing controls, opacity, and
other presentation changes create a new visualization object and therefore
invalidated both pipelines without changing their inputs.

The memo dependency now uses an exact JSON key of `visibleResultLayers`.
Result identity, board geometry, analysis-net scope, active layer, isolated net,
board-layer visibility, analysis-only state, and result mode remain explicit
dependencies. Changing any input actually read by either pipeline still
recomputes it. Solver data, field values, filtering, spatial thinning, and
rendering limits are unchanged.

## Reproduction and evidence

From `app` run:

```text
node scripts/test-layout-result-memoization.mjs
npm run test:result-performance
```

The bounded workload applies 40 playback-only updates to 50,000 scalar samples.
It reproduces 40 dense scans with the prior whole-object dependency and zero
with the selected-layer dependency. Five fresh Node processes measured the
representative scalar scan work at 39.46, 49.23, 42.04, 49.07, and 51.88 ms.
Raw parameters, source hashes, runtime, revision, and results are in
`output/performance-20261024/layout-result-memoization/benchmark.json`.

The regression check inspects both field and vector memo dependency lists and
asserts that unrelated visualization state cannot invalidate them. It also
checks missing, ordered, and reordered layer selections.

## Limits

The timing isolates the redundant CPU scan; it is not a full React-frame, SVG,
GPU, native transport, project-loading, or solver benchmark. A result, board,
net scope, visible board layer, active result layer, or result mode change still
performs the complete exact pipeline. This change makes no universal
millisecond-response claim.
