# Result scalar presentation performance - 23 October 2026

## Scope

This check covers presentation-only work in the Results panel. It does not
change solver samples, field admission, numerical values, mesh preparation, or
viewport rendering. The panel previously filtered the active scalar field and
performed two full sorts on every React render, including renders caused by
unrelated controls.

`resultScalarPresentation` retains that exact filter and stable-sort behavior
on the first request and caches the immutable field/layer result by source-array
identity. Each field retains at most eight layer-selection summaries.
The active result's mesh/vector/layer inventory is likewise reused by result
identity and active scalar field; inactive scalar fields remain excluded exactly
as before.

## Reproduction

From `app` run:

```text
node scripts/test-result-scalar-presentation.mjs
npm run test:result-performance
```

The focused workload contains 100,000 scalar samples, of which 75,000 match
`F.Cu`. It compares the prior filter/value-sort/hotspot-sort sequence with a
cold cached-helper request and 20 repeated requests. The correctness fixture
also asserts exact sample and hotspot identities for unmasked, masked,
through-layer, and malformed non-finite rows.

Five fresh-process runs are recorded in
`output/performance-20261023/result-scalar-presentation/benchmark.json`, along
with the Git revision, source hashes, runtime, and parameters. Baseline medians
ranged from 45.73 to 93.10 ms. Cold helper calls ranged from 44.35 to 57.48 ms,
so this change makes no cold-path speedup claim. Warm median lookups ranged from
0.0009 to 0.0011 ms because filtering and sorting were reused.

## Limits

The cache assumes normalized solver field arrays are immutable, matching the
existing result presentation contract. A newly materialized field array or a
new layer selection performs the full exact calculation once. Browser render,
GPU upload, Plotly work, native transport, solver execution, and large assembly
scene costs are outside this benchmark.
