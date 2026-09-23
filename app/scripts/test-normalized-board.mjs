import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { createHash } from "node:crypto";
import { deflateSync } from "node:zlib";
import { hydrateNormalizedSnapshot, compressNormalizedSnapshot } from "../src/normalizedSnapshotTransport.ts";

const source = readFileSync(new URL("../src/normalizedBoard.ts", import.meta.url), "utf8");
const module = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { parseNormalizedBoard, normalizedDesignSnapshot, normalizedSolverDesign } = await import(`data:text/javascript;base64,${Buffer.from(module).toString("base64")}`);
const ring = (x, y, w) => ({ role: "outer", start_mm: [x,y], segments: [
  {kind:"line", end_mm:[x+w,y]}, {kind:"line", end_mm:[x+w,y+w]}, {kind:"line", end_mm:[x,y+w]}, {kind:"line", end_mm:[x,y]}] });
const design = { contract:"spike/v1", layers:[{name:"top", type:"signal"}], nets:[{id:1,name:"GND"}], tracks:[], vias:[], pads:[], components:[], stackup:[],
  zones:[{id:"z", layer:"top", net_id:1, boundary_rings:[ring(0,0,10), {...ring(2,2,2), role:"cutout"}]}],
  metadata:{board_bounds_mm:[0,0,10,10], board_outline_rings:[ring(0,0,10)], arcs:[{id:"a", start:[0,1], end:[1,0], center:[0,0], clockwise:true, width:.2, layer:"top", net_id:1}]} };
const snapshot = JSON.stringify({contract:"spike/design-snapshot/v1", design});
const board = parseNormalizedBoard(snapshot);
assert.equal(board.width,10);
assert.equal(board.zones[0].holes.length,1);
assert.equal(board.zones[0].net,"GND");
assert.ok(board.tracks.length >=8);
assert.deepEqual(board.tracks.at(-1).end,[1,0]);
assert.deepEqual(normalizedDesignSnapshot(snapshot).design,design);
assert.throws(()=>parseNormalizedBoard('{"contract":"other"}'));

const kicadDesign = {
  contract:"spike/v1",
  layers:[{name:"F.Cu",type:"signal"},{name:"B.Cu",type:"signal"}], nets:[], tracks:[], vias:[], zones:[], stackup:[],
  pads:[{id:"p1",name:"1",component:"U1",at:[12,7],size:[1.5,2],layers:["B.Cu"],layer:"B.Cu",rotation:180}],
  components:[{id:"c1",reference:"U1",library:"Package_QFP:LQFP-48",at:[12,7],rotation:180,layer:"B.Cu"}],
  metadata:{board_bounds_mm:[10,5,30,15],board_outline_drawings:[
    {type:"line",start:[10,5],end:[30,5],layer:"Edge.Cuts",width:.05},
    {type:"line",start:[30,5],end:[30,15],layer:"Edge.Cuts",width:.05},
    {type:"line",start:[30,15],end:[10,15],layer:"Edge.Cuts",width:.05},
    {type:"line",start:[10,15],end:[10,5],layer:"Edge.Cuts",width:.05},
  ]},
};
const kicadBoard = parseNormalizedBoard(JSON.stringify({contract:"spike/design-snapshot/v1",design:kicadDesign}));
assert.equal(kicadBoard.drawings.length,4,"canonical KiCad outline drawings must remain drawable");
assert.equal(kicadBoard.outlineLoops.length,1,"canonical KiCad outline drawings must form the display substrate");
assert.deepEqual(kicadBoard.outlineLoops[0][0],[10,5]);
assert.deepEqual(kicadBoard.pads[0].at,[12,7]);
assert.equal(kicadBoard.pads[0].name,"1");
assert.equal(kicadBoard.components[0].library,"Package_QFP:LQFP-48");
assert.equal(kicadBoard.components[0].layer,"B.Cu","legacy normalized KiCad components must retain their source side");
assert.deepEqual(kicadBoard.components[0].at,[12,7]);
console.log("Normalized display projection preserves hole geometry and keeps exact solver source independent.");

const artworkSnapshot = {contract:"spike/design-snapshot/v1", design: {...design, metadata:{...design.metadata, odb_artwork:[
  {id:"silk-track",kind:"track",start:[1,1],end:[4,1],width:.1,layer:"legend"},
  {id:"mask-pad",kind:"pad",at:[5,5],size:[2,1],layers:["mask"],layer:"mask",shape:"rect"},
  {id:"paste-zone",kind:"zone",layer:"paste",boundary_rings:[ring(6,6,1)]},
]}}};
const artworkBoard = parseNormalizedBoard(JSON.stringify(artworkSnapshot));
assert.ok(artworkBoard.tracks.some(t=>t.id==="silk-track"));
assert.ok(artworkBoard.pads.some(p=>p.id==="mask-pad" && p.width===2));
assert.ok(artworkBoard.zones.some(z=>z.id==="paste-zone"));
assert.equal(artworkSnapshot.design.tracks.length, 0, "display artwork must never become solver copper");
const compact = structuredClone(artworkSnapshot);
compact.canonical_design = { metadata: { odb_artwork: compact.design.metadata.odb_artwork } };
delete compact.design.metadata.odb_artwork;
compact.design.components = [{ id: "pkg", reference: "U1", at: [5,5], side: "top", odb_package_ref: { index: 3, bounds_mm: [-4,-2,4,2] } }];
const compactBoard = parseNormalizedBoard(JSON.stringify(compact));
assert.deepEqual(compactBoard.tracks, artworkBoard.tracks, "compact transport retains canonical technical artwork");
assert.deepEqual(compactBoard.zones, artworkBoard.zones);
assert.equal(compactBoard.components[0].width, 8);
assert.equal(compactBoard.components[0].height, 4);
compact.design.pads = [{id:"custom",at:[1,1],size:[2,2],layer:"top",layers:["top"],shape:"custom",custom_geometry:{status:"supported",positive_filled_polygon:[[-1,0],[0,1],[1,0],[0,-1]]}}];
assert.deepEqual(parseNormalizedBoard(JSON.stringify(compact)).pads[0].customPolygon,[[-1,0],[0,1],[1,0],[0,-1]]);
compact.design.layers.push({name:"DRILL_F.CU-B.Cu",type:"drill"});
assert.deepEqual(parseNormalizedBoard(JSON.stringify(compact)).layers, ["top"], "drill span names ending in .Cu must not become conductors");
compact.design.zones = [];
compact.canonical_design.layers = [{id:"layer-top",name:"top"}];
compact.canonical_design.nets = [{id:"net-gnd",name:"GND"}];
compact.canonical_design.zones = [{id:"zone-uuid",source_id:"z",layer_ids:["layer-top"],net_id:"net-gnd",boundary_rings:design.zones[0].boundary_rings}];
compact.canonical_design.metadata.transport_projection = {legacy_omitted_collections:["zones"]};
assert.deepEqual(parseNormalizedBoard(JSON.stringify(compact)).zones, artworkBoard.zones, "canonical-only transport retains copper zones, holes and net identities");
assert.throws(()=>normalizedSolverDesign(JSON.stringify(compact)), /transport hydration/, "wire-only omissions must never silently become solver inputs");
const zoneBytes = Buffer.from(JSON.stringify(design.zones));
compact.canonical_design.metadata.transport_projection.legacy_zones_archive = {
  encoding:"zlib+base64+json",bytes:zoneBytes.length,count:design.zones.length,
  sha256:createHash('sha256').update(zoneBytes).digest('hex'),data:deflateSync(zoneBytes).toString('base64'),
};
const hydrated = await hydrateNormalizedSnapshot(JSON.stringify(compact));
assert.deepEqual(normalizedSolverDesign(hydrated).zones,design.zones,"solver receives the exact legacy rows, including holes and source identities");
assert.deepEqual(parseNormalizedBoard(hydrated).zones,artworkBoard.zones);
assert.equal(await hydrateNormalizedSnapshot(hydrated),hydrated,"reopen of hydrated snapshots is idempotent");
const packagedSource = await compressNormalizedSnapshot(hydrated);
assert.equal(await hydrateNormalizedSnapshot(packagedSource),hydrated,"compressed .spike source preserves every original UTF-8 byte");
const canonicalOmitted = JSON.parse(hydrated);
const reopenCanonical = canonicalOmitted.canonical_design;
delete canonicalOmitted.canonical_design;
const compactReopen = JSON.parse(await compressNormalizedSnapshot(JSON.stringify(canonicalOmitted)));
compactReopen.canonical_design_omitted = true;
await assert.rejects(()=>hydrateNormalizedSnapshot(JSON.stringify(compactReopen)), /missing its canonical design/);
assert.deepEqual(JSON.parse(await hydrateNormalizedSnapshot(JSON.stringify(compactReopen), reopenCanonical)), JSON.parse(hydrated), "compact native reopen restores the authoritative canonical design");
assert.deepEqual(JSON.parse(await hydrateNormalizedSnapshot(compactReopen, reopenCanonical)), JSON.parse(hydrated), "native object wrapper and string wrapper have identical hydration");
const damagedSource = JSON.parse(packagedSource);
damagedSource.sha256='0'.repeat(64);
await assert.rejects(()=>hydrateNormalizedSnapshot(JSON.stringify(damagedSource)),/checksum/);
const badTransport = structuredClone(compact);
badTransport.canonical_design.metadata.transport_projection.legacy_zones_archive.sha256='0'.repeat(64);
await assert.rejects(()=>hydrateNormalizedSnapshot(JSON.stringify(badTransport)),/checksum/);
badTransport.canonical_design.metadata.transport_projection.legacy_zones_archive.bytes=2;
await assert.rejects(()=>hydrateNormalizedSnapshot(JSON.stringify(badTransport)),/declared size/);
delete compact.canonical_design.zones;
assert.throws(()=>parseNormalizedBoard(JSON.stringify(compact)), /missing its canonical zone/);
for (const filename of process.argv.slice(2)) {
  const input = readFileSync(filename,"utf8");
  const envelope = JSON.parse(input);
  const source = await hydrateNormalizedSnapshot(envelope.result?.project?.design?.source_board ?? input, envelope.result?.canonical?.design_ir);
  const parsed = parseNormalizedBoard(source);
  const solver = normalizedSolverDesign(source);
  assert.ok(Array.isArray(solver.zones));
  assert.ok(parsed.layers.length > 0 && parsed.outlineLoops.length > 0);
  for (const p of parsed.pads) assert.ok(p.at.every(Number.isFinite) && p.width > 0 && p.height > 0);
  for (const t of parsed.tracks) assert.ok([...t.start,...t.end,t.width].every(Number.isFinite));
  console.log(JSON.stringify({file:filename,tracks:parsed.tracks.length,pads:parsed.pads.length,vias:parsed.vias.length,components:parsed.components.length,zones:parsed.zones.length,solverZones:solver.zones.length,copper:parsed.layers.length,drawable:parsed.layerDefinitions.length}));
}
