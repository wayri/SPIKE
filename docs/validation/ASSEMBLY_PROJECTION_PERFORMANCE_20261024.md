<!-- SPDX-License-Identifier: Apache-2.0 -->
# Assembly occurrence projection performance, 2026-10-24

## Scope

This change removes repeated retained-design presentation work from
`buildVirtualBoardVisualization`. Repeated physical board occurrences still
receive independent IDs, names, transforms and active-selection state. Net IDs,
net names, retained source identity and board envelope remain derived from the
same retained design payload.

The projection now prepares the board envelope, source native ID and both net
identity maps once per retained `design_id` for one projection call. Every
occurrence of that design shares those `Object.freeze`-enforced immutable maps. The previous loop rebuilt
both maps for every occurrence and searched prior visuals to assign the active
occurrence.

## Bounded evidence

`app/scripts/test-harness-visualization.mjs` projects 30 occurrences of one
retained design containing 10,000 nets. Getter instrumentation measures exactly
20,000 retained net-field reads in the current implementation: one `id` and one
`name` read per net. The previous occurrence-local construction performed
600,000 reads for the same fixture and allocated 60 net maps instead of two.
This is a 30x reduction in the measured retained-net traversal count.

The fixture also verifies all 30 occurrence rows survive, assignment and deletion
against either shared map throw, rejected mutation leaves sibling identity exact,
the retained source is unchanged, and exactly the first occurrence of the active
design is active. Existing harness and four-board XYZ placement assertions
continue to cover independent transforms and connector endpoints.

This is a bounded synthetic projection check. It does not establish native
frame rate, GPU memory, project-open time or 10/20-board end-to-end latency.
Those checks remain deferred until the required free-memory gate is met.

## Reproduction

From `app`:

```powershell
node scripts/test-harness-visualization.mjs
npm.cmd run test:harness-visualization
npm.cmd exec tsc -- --noEmit
```
