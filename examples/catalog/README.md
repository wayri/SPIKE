<!-- SPDX-License-Identifier: Apache-2.0 -->
# Curated work examples

`work-examples.json` is the human-readable index for the desktop **Work examples**
catalog. It selects original SPIKE inputs and small runners already in this
repository. This change adds presentation and packaging only; it adds no solver
or physics formulation. Each fixture retains its recorded license. The two
older SigHarmonic SI numerical fixtures remain MIT. EMerge library navigation
uses the existing library and retains its per-entry source and license boundary;
this index does not copy external models or source.

Every card includes three steps, engine and runtime prerequisites, limitations,
and an explicit readiness state:

- `runnable`: an executable source workflow with its listed dependencies. This
  is not an installed-runtime probe or evidence of a new execution.
- `setup-only`: a draft, request or geometry input still needing explicit setup,
  identity binding or runtime preparation.
- `saved-evidence`: retained original inputs/results that can be inspected
  without a new execution. Their original limitations remain in force.
- `guide`: opens an existing library with its own per-entry prerequisites.

Use **Inspect text** to review an exact bundled source asset, select a companion
file, then **Save selected file**. In a browser this downloads a file; the desktop
uses the existing artifact save dialog with the exact file suffix and a SHA-256
content check. Scripts must remain in their original
relative locations inside a source checkout with development dependencies.
Saving a runner alone does not install SPIKE's Python/native implementation.
Source commands run from the repository root; choose fresh output destinations.
No source is executed by opening, inspecting, saving or staging an example.

The explicit **Stage IBIS example** action loads the inline-source request into
the existing behavioral workbench. Compilation and consented trusted ngspice
execution retain their separate controls. The strict 0.5 mV refinement criterion
remains unmet for the retained execution evidence.

**Stage spatial SI example** uses the normalized `board.spike-design.json`
snapshot with its canonical-v2 payload and legacy viewport projection, plus
`solver.json` and `samples.json`. The parent applies its normal unsaved-project
guard and stages data in the existing SI panel. Sample admission still requires
an exact current design/occurrence binding; normalization or edits may require a
new explicit supplied-pair run. This is voltage sampling, not an E-field solve.

`app/src/workExampleAssets.ts` is the fixed Vite `?raw` allowlist. Resources load
on demand; the catalog never scans arbitrary folders or bundles large geometry,
images, binaries or external example trees. Its loader rejects assets outside
the selected entry and text above 512 KiB.

The public component API is `WorkExamples({ onOpen? })`. Its callback receives
`(entryId, action)` with `action.kind` equal to `emerge-library`, `ibis` (inert
`requestText`), or `spatial` (inert `designText`, `solverText`, `samplesText`). The
parent owns workspace mutation and execution authority. A missing callback
disables staging while file inspection/saving remains available. Async failures
and cancelled native saves remain visible in each card.

From `app`, run `node scripts/test-work-examples.mjs` and
`npm run test:button-standard`. These verify the manifest, resource allowlist,
filtering, staging payloads, source rendering, interactive controls and error
recovery without starting a solver. Native wide/narrow window acceptance and
installed-runtime qualification remain separate checks.
