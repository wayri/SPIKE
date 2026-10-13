// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

assert.match(source, /import SmpsConverterPanel,[\s\S]*validSmpsConverterResult[\s\S]*from "\.\/SmpsConverterPanel"/);
assert.match(source, /import PiReturnPathAssistant,[\s\S]*PiReturnPathSelection[\s\S]*from "\.\/PiReturnPathAssistant"/);
assert.match(source, /import CapacitorPlacementPanel,[\s\S]*parseCapacitorPlacementRequest[\s\S]*validCapacitorPlacementResult[\s\S]*from "\.\/CapacitorPlacementPanel"/);

// The request and admitted result are part of PiSetup, so the existing study
// and project snapshot paths retain them with the rest of the PI setup.
assert.match(source, /type PiSetup = \{[\s\S]*smpsConverter: \{ request: SmpsConverterRequest \| null; result: SmpsConverterResult \| null \}/);
assert.match(source, /type PiSetup = \{[\s\S]*capacitorPlacement: \{ request: CapacitorPlacementRequest \| null; result: CapacitorPlacementResult \| null \}/);
assert.match(source, /const defaultPiSetup[\s\S]*smpsConverter: \{ request: null, result: null \}/);
assert.match(source, /const defaultPiSetup[\s\S]*capacitorPlacement: \{ request: null, result: null \}/);
assert.match(source, /const normalizePiSetup[\s\S]*validSmpsRequestSnapshot\(smpsSnapshot\?\.request\)[\s\S]*validSmpsConverterResult\(smpsSnapshot\?\.result, smpsRequest\)[\s\S]*smpsConverter: \{ request: smpsRequest, result: smpsResult \}/);
assert.match(source, /const normalizePiSetup[\s\S]*parseCapacitorPlacementRequest\(JSON\.stringify\(capacitorSnapshot\.request\)\)[\s\S]*validCapacitorPlacementResult\(capacitorSnapshot\?\.result, capacitorRequest\)[\s\S]*capacitorPlacement: \{ request: capacitorRequest, result: capacitorResult \}/);
assert.match(source, /snapshot = \(\): ProjectSnapshot => \([\s\S]*piSetup: structuredClone\(piSetup\)/);
assert.match(source, /analysis: retainOpaqueResultState[\s\S]*pi_setup: piSetup/);

// Component identities come from the loaded board and a retained occurrence.
assert.match(source, /const smpsComponents = useMemo[\s\S]*board\.components\.flatMap[\s\S]*reference: component\.ref/);
assert.match(source, /occurrenceId: retainedOccurrenceId/);
assert.match(source, /occurrenceId=\{piAnalysisOccurrenceId\}/);
assert.doesNotMatch(source, /occurrenceId=\{[^}]*boardFile/);
assert.match(source, /selectedPiOccurrence\.designId === activeDesignId/);
assert.match(source, /<SmpsConverterPanel workerAvailable=\{workerAvailable\} components=\{smpsComponents\}[\s\S]*initialRequest=\{setup\.smpsConverter\.request\}[\s\S]*smpsConverter: \{ request, result \}/);
assert.match(source, /<CapacitorPlacementPanel workerAvailable=\{workerAvailable\}[\s\S]*initialRequest=\{setup\.capacitorPlacement\.request\} initialResult=\{setup\.capacitorPlacement\.result\}[\s\S]*capacitorPlacement: \{ request, result \}/);

// The assistant receives the same retained design object used to build PI
// requests. Apply resolves exact pads and preserves solver load-pair ordering.
assert.match(source, /const design = analysisDesign;[\s\S]*if \(!design\) throw new Error/);
assert.match(source, /<PiReturnPathAssistant workerAvailable=\{workerAvailable\} design=\{analysisDesign\}/);
assert.match(source, /selection\.loadPadIds\.length !== setup\.loads\.length/);
assert.match(source, /board\.pads\.find\(pad => pad\.id === selection\.sourcePadId\)/);
assert.match(source, /selection\.loadPadIds\.map\(id => board\.pads\.find\(pad => pad\.id === id\)\)/);
assert.match(source, /sourcePad\.net !== selection\.returnNet \|\| loadPads\.some/);
assert.match(source, /mode: "explicit"[\s\S]*sources: \[retainedTerminal[\s\S]*loads: loadPads\.map\(\(pad, index\) => retainedTerminal[\s\S]*current\.loads\[index\]/);
assert.match(source, /returnPath\.loads\.map\(\(item, index\)[\s\S]*pair_id: `load-pair-\$\{index \+ 1\}`/);

console.log("PI engineering assistants retain converter and capacitor snapshots and apply exact ordered return-pad pairs.");
