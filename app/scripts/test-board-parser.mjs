import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const parserSource = readFileSync(new URL("../src/boardParser.ts", import.meta.url), "utf8");
const numericRangeSource = readFileSync(new URL("../src/numericRange.ts", import.meta.url), "utf8");
const kikakukaFlexSource = readFileSync(new URL("../src/kikakukaFlex.ts", import.meta.url), "utf8");
const compilerOptions = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 };
const numericRangeModule = ts.transpileModule(numericRangeSource, {
  compilerOptions,
}).outputText;
const numericRangeUrl = `data:text/javascript;base64,${Buffer.from(numericRangeModule).toString("base64")}`;
const kikakukaFlexModule = ts.transpileModule(kikakukaFlexSource, { compilerOptions }).outputText;
const kikakukaFlexUrl = `data:text/javascript;base64,${Buffer.from(kikakukaFlexModule).toString("base64")}`;
const transpiled = ts.transpileModule(parserSource, {
  compilerOptions,
}).outputText
  .replace('from "./numericRange";', `from "${numericRangeUrl}";`)
  .replace('from "./kikakukaFlex";', `from "${kikakukaFlexUrl}";`);
const parser = await import(`data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`);
for (const filename of process.argv.slice(2)) {
  const started = performance.now();
  const parsed = parser.parseKicadBoard(readFileSync(filename, "utf8"));
  if (filename.replaceAll("\\", "/").endsWith("/ebrake1.kicad_pcb")) {
    assert.equal(parsed.zones.length, 26, "placement keepouts must not masquerade as copper zones");
    assert.ok(parsed.zones.every(zone => zone.filled_copper_state === "source_filled" && zone.source_fill_provenance_complete));
    const q1 = parsed.pads.filter(pad => pad.ref === "Q1");
    assert.equal(q1.length, 4);
    assert.equal(q1.filter(pad => pad.type === "np_thru_hole").length, 1, "empty quoted pad names must retain token positions");
    assert.equal(q1.filter(pad => pad.type === "thru_hole").length, 3);
    assert.deepEqual(q1.find(pad => pad.name === "1")?.drill_size, [1.1, 1.1]);
  }
  console.log(JSON.stringify({ file: filename, ms: Math.round(performance.now() - started), components: parsed.components.length, pads: parsed.pads.length, vias: parsed.vias.length, tracks: parsed.tracks.length, zones: parsed.zones.length, copper: parsed.layers.length, layers: parsed.layerDefinitions.length }));
}

const copperNames = ["F.Cu", ...Array.from({ length: 30 }, (_, index) => `In${index + 1}.Cu`), "B.Cu"];
const copperRows = copperNames.map((name, index) => {
  const id = name === "F.Cu" ? 0 : name === "B.Cu" ? 2 : (index + 1) * 2;
  const userName = name === "In10.Cu" ? ' "MEMORY_PWR"' : "";
  return `    (${id} "${name}" ${index % 3 === 0 ? "power" : "signal"}${userName})`;
}).join("\n");
const board = `(kicad_pcb
  (version 20241229)
  (generator pcbnew)
  (layers
${copperRows}
    (7 "B.SilkS" user "Bottom Silkscreen")
    (5 "F.SilkS" user "Top Silkscreen")
    (25 "Edge.Cuts" user)
  )
  (setup (stackup
    (layer "F.Cu" (type "copper") (thickness 0.035))
    (layer "F.Mask" (type "solder mask") (color "red") (thickness 0.01))
    (layer "dielectric 1" (type "core") (thickness 1.53) (epsilon_r 4.2))
    (layer "B.Cu" (type "copper") (thickness 0.035))
  ))
  (net 0 "")
  (net 1 "VCC")
  (segment (start 1 1) (end 9 1) (width 0.25) (layer "In30.Cu") (net 1))
)`;

const parsed = parser.parseKicadBoard(board);
assert.deepEqual(parsed.layers, copperNames, "all copper layers must retain KiCad physical order");
assert.equal(parsed.layerDefinitions.length, 35, "all enabled board layers must be retained");
assert.equal(parsed.layerDefinitions.find(layer => layer.name === "In10.Cu")?.userName, "MEMORY_PWR");
assert.equal(parsed.tracks[0].layer, "In30.Cu");
assert.equal(parsed.stackup.find(layer => layer.name === "F.Mask")?.color, "red", "source finish color must survive import");
assert.equal(
  parser.isCopperLayerDefinition({ id: 96, name: "POWER_CORE_32", kind: "power" }),
  true,
  "semantic copper layers must not be capped by numeric ID",
);

const footprintMetadata = parser.parseKicadBoard(`(kicad_pcb
  (version 20241229)
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "B.SilkS" user) (37 "F.SilkS" user)
    (44 "Edge.Cuts" user) (48 "B.Fab" user) (49 "F.Fab" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user))
  (footprint "Package_SO:TSSOP-8" (layer "F.Cu") (at 20 30 90)
    (property "Reference" "U1")
    (property "Value" "TEST_IC")
    (property "Height" "6.5mm")
    (fp_rect (start -2 -1.5) (end 2 1.5) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))
    (fp_rect (start -2.4 -1.9) (end 2.4 1.9) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
    (pad "1" smd rect (at -2.7 -1) (size 1.4 0.6) (layers "F.Cu" "F.Paste" "F.Mask"))
    (pad "2" smd rect (at 2.7 1) (size 1.4 0.6) (layers "F.Cu" "F.Paste" "F.Mask"))
    (model "\${KICAD9_3DMODEL_DIR}/Package_SO.3dshapes/TSSOP-8.wrl"
      (offset (xyz 1 2 3)) (scale (xyz 1 1.5 2)) (rotate (xyz 10 20 30)))
    (model "local/marker.step"
      (offset (xyz -4 -5 -6)) (scale (xyz .5 .5 .5)) (rotate (xyz 0 90 0)))))`);
assert.deepEqual(footprintMetadata.components[0].properties.find(row=>row.name==="Height").values,["6.5mm"],"KiCad custom height fields survive parsing");
assert.deepEqual(footprintMetadata.components[0].bodyBounds, { minX: -2, minY: -1.5, maxX: 2, maxY: 1.5 });
assert.deepEqual(footprintMetadata.components[0].courtyardBounds, { minX: -2.4, minY: -1.9, maxX: 2.4, maxY: 1.9 });
assert.deepEqual(footprintMetadata.components[0].models, [
  { path: "${KICAD9_3DMODEL_DIR}/Package_SO.3dshapes/TSSOP-8.wrl", offset: [1, 2, 3], scale: [1, 1.5, 2], rotation: [10, 20, 30] },
  { path: "local/marker.step", offset: [-4, -5, -6], scale: [.5, .5, .5], rotation: [0, 90, 0] },
], "all per-footprint model transforms must survive parsing in source order");
assert.deepEqual(footprintMetadata.components[0].modelOffset, [1, 2, 3], "legacy singular transform aliases the first model");
const duplicatedOutline = parser.parseKicadBoard(`(kicad_pcb
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (gr_line (start 10 20) (end 78.58 20) (layer "Edge.Cuts"))
  (gr_line (start 78.58 20) (end 10 20) (layer "Edge.Cuts"))
  (gr_line (start 78.58 20) (end 78.58 73.34) (layer "Edge.Cuts"))
  (gr_line (start 78.58 20) (end 78.58 73.34) (layer "Edge.Cuts"))
  (gr_line (start 78.58 73.34) (end 10 73.34) (layer "Edge.Cuts"))
  (gr_line (start 10 73.34) (end 10 20) (layer "Edge.Cuts"))
  (gr_circle (center 13 23) (end 14 23) (layer "Edge.Cuts")))`);
assert.equal(duplicatedOutline.drawings.length, 7, "source drawings remain intact");
assert.equal(duplicatedOutline.outlineLoops.length, 2, "duplicate edges must not close tiny retraced loops");
assert.deepEqual(duplicatedOutline.bounds, {minX:10,minY:20,maxX:78.58,maxY:73.34});
assert.ok(Math.abs(duplicatedOutline.width - 68.58) < 1e-9);
const separatePanels = parser.parseKicadBoard(`(kicad_pcb
  (gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))
  (gr_rect (start 50 0) (end 70 10) (layer "Edge.Cuts")))`);
assert.equal(separatePanels.width, 70, "bounds include every board outline island");
const kikakukaBoard = parser.parseKicadBoard(`(kicad_pcb
  (version 20250114)
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "User.4" user "fReEkIcAd") (44 "Edge.Cuts" user))
  (setup (stackup
    (layer "F.Cu" (type "copper") (thickness 0.035))
    (layer "dielectric 1" (type "core") (thickness 0.13))
    (layer "B.Cu" (type "copper") (thickness 0.035))))
  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
  (gr_line (start 3 0) (end 3 10) (layer "User.4") (uuid "bend-span"))
  (gr_text "s=0.942477796076938mm a=90" (at 3.1 0) (layer "User.4"))
  (gr_line (start 6 0) (end 6 10) (layer "User.4") (uuid "bend-radius"))
  (gr_text "s=4mm r=0.2cm a=-70deg" (at 6 0) (layer "User.4"))
  (gr_line (start 8 0) (end 8 10) (layer "User.4") (uuid "bend-unset"))
  (gr_line (start 8.5 0) (end 8.5 10) (layer "User.4") (uuid "bend-zero"))
  (gr_text "a=90 r=0" (at 8.5 0) (layer "User.4"))
  (gr_line (start 9 0) (end 9 10) (layer "User.4") (uuid "bend-bad"))
  (gr_text "a=oops r=bad" (at 9 0) (layer "User.4"))
  (gr_text "a=45" (at 9 0.01) (layer "User.4"))
  (gr_line (start 9.5 0) (end 9.5 10) (layer "User.4") (uuid "bend-negative"))
  (gr_text "a=90 r=-1mm" (at 9.5 0) (layer "User.4")))`);
assert.equal(kikakukaBoard.technology, "flex", "FreekiCAD-only boards are identified as flexible display metadata");
assert.equal(kikakukaBoard.bendLines.length, 6, "every FreekiCAD line remains an editable bend");
assert.equal(kikakukaBoard.regions[0].source, "implicit-board-outline");
const [spanBend, radiusBend, unsetBend, zeroBend, malformedBend, negativeBend] = kikakukaBoard.bendLines;
assert.equal(spanBend.format, "kikakuka/freekicad-v1");
assert.equal(spanBend.sourceLayer, "User.4");
assert.equal(spanBend.sourceLayerUserName, "fReEkIcAd");
assert.equal(spanBend.sourceDrawingId, "bend-span");
assert.deepEqual(spanBend.annotationPosition, [3.1, 0]);
assert.ok(Math.abs(spanBend.radiusMm - .5) < 1e-12);
assert.equal(spanBend.radiusSource, "s");
assert.equal(radiusBend.radiusMm, 2);
assert.equal(radiusBend.radiusSource, "r", "r takes precedence over s");
assert.ok(radiusBend.issues.some(issue => issue.code === "KIKAKUKA_BEND_RADIUS_PRECEDENCE"));
assert.equal(unsetBend.configured, false);
assert.ok(unsetBend.issues.some(issue => issue.code === "KIKAKUKA_BEND_ANNOTATION_MISSING"));
assert.ok(malformedBend.issues.some(issue => issue.code === "KIKAKUKA_BEND_ANNOTATION_CONFLICT"));
assert.ok(malformedBend.issues.some(issue => issue.code === "KIKAKUKA_BEND_ANNOTATION_MALFORMED"));
assert.equal(zeroBend.radiusMm, 0, "zero is a valid bend radius");
assert.ok(!zeroBend.issues.some(issue => issue.code === "KIKAKUKA_BEND_RADIUS_NEGATIVE"));
assert.ok(negativeBend.issues.some(issue => issue.code === "KIKAKUKA_BEND_RADIUS_NEGATIVE"));
const kikakukaNumeric = parser.parseKicadBoard(`(kicad_pcb
  (version 20250114)
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "User.4" user "FreekiCAD") (44 "Edge.Cuts" user))
  (setup (stackup
    (layer "F.Cu" (type "copper") (thickness 0.035))
    (layer "dielectric 1" (type "core") (thickness 0.13))
    (layer "B.Cu" (type "copper") (thickness 0.035))))
  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
  (gr_line (start 1 0) (end 1 10) (layer "User.4") (uuid "exact"))
  (gr_text "a=90 r=.5mm" (at 1.1 0) (layer "User.4"))
  (gr_line (start 2 0) (end 2 10) (layer "User.4") (uuid "outside"))
  (gr_text "a=90 r=.6mm" (at 2.10001 0) (layer "User.4"))
  (gr_line (start 3 0) (end 3 10) (layer "User.4") (uuid "zero-angle"))
  (gr_text "a=0 s=1mm" (at 3 0) (layer "User.4"))
  (gr_line (start 4 0) (end 4 10) (layer "User.4") (uuid "derived-overflow"))
  (gr_text "a=1e-9 s=1e308mm" (at 4 0) (layer "User.4"))
  (gr_line (start 5 0) (end 5 10) (layer "User.4") (uuid "literal-overflow"))
  (gr_text "a=90 r=1e999" (at 5 0) (layer "User.4"))
  (gr_line (start 6 0) (end 6 10) (layer "User.4") (uuid "unit-overflow"))
  (gr_text "a=90 r=1e308cm" (at 6 0) (layer "User.4")))`);
const [exactEdge, outsideEdge, zeroAngle, derivedOverflow, literalOverflow, unitOverflow] = kikakukaNumeric.bendLines;
assert.equal(exactEdge.radiusMm, .5, "an annotation exactly 0.1 mm from an endpoint is associated");
assert.equal(outsideEdge.annotation, undefined, "an annotation outside 0.1 mm remains orphaned");
assert.ok(outsideEdge.issues.some(issue => issue.code === "KIKAKUKA_BEND_ANNOTATION_MISSING"));
assert.ok(kikakukaNumeric.flexIssues.some(issue => issue.code === "KIKAKUKA_ANNOTATION_ORPHAN"));
assert.equal(zeroAngle.radiusMm, undefined);
assert.ok(zeroAngle.issues.some(issue => issue.code === "KIKAKUKA_BEND_SPAN_NEEDS_ANGLE"));
assert.equal(derivedOverflow.radiusMm, undefined);
assert.ok(derivedOverflow.issues.some(issue => issue.code === "KIKAKUKA_BEND_RADIUS_NONFINITE"));
for (const bend of [literalOverflow, unitOverflow]) {
  assert.equal(bend.radiusMm, undefined);
  assert.ok(bend.issues.some(issue => issue.code === "KIKAKUKA_BEND_ANNOTATION_MALFORMED"));
}
assert.ok(!JSON.stringify(kikakukaNumeric.bendLines).includes('"radiusMm":null'), "non-finite radii never serialize as JSON null");
const spanOnlyBoard = stackup => parser.parseKicadBoard(`(kicad_pcb
  (version 20250114)
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "User.4" user "FreekiCAD") (44 "Edge.Cuts" user))
  ${stackup}
  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
  (gr_line (start 5 0) (end 5 10) (layer "User.4"))
  (gr_text "a=90 s=1mm" (at 5 0) (layer "User.4")))`);
for (const boardWithBadThickness of [spanOnlyBoard(""), spanOnlyBoard('(setup (stackup (layer "F.Cu" (type "copper") (thickness 1e308)) (layer "B.Cu" (type "copper") (thickness 1e308))))')]) {
  assert.equal(boardWithBadThickness.bendLines[0].radiusMm, undefined);
  assert.ok(boardWithBadThickness.bendLines[0].issues.some(issue => issue.code === "KIKAKUKA_BEND_SPAN_NEEDS_THICKNESS"));
}
console.log(`boardParser high-layer and duplicate-outline regressions passed: ${parsed.layers.length} copper / ${parsed.layerDefinitions.length} total layers`);

for (const token of ["footprint", "module"]) {
  for (const side of ["F.Cu", "B.Cu"]) {
    for (const angle of [undefined, 0, 23, 90]) {
      const board = parser.parseKicadBoard(`(kicad_pcb (version 20240108)
        (layers (0 "F.Cu" signal) (31 "B.Cu" signal))
        (${token} "Fixture:PadFrame" (layer "${side}") (at 20 10 90)
          (property "Reference" "J1")
          (pad "1" smd rect (at 2 1${angle === undefined ? "" : ` ${angle}`})
            (size 1.2 .8) (layers "${side}"))))`);
      assert.ok(Math.abs(board.pads[0].at[0] - 21) < 1e-9);
      assert.ok(Math.abs(board.pads[0].at[1] - 8) < 1e-9);
      assert.equal(board.pads[0].rotation, angle ?? 0, "native pad angle is absolute on both sides");
    }
  }
}
