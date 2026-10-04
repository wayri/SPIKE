// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const modelBundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/scriptResultViewportModel.ts", import.meta.url))],
  bundle: true, write: false, format: "esm", platform: "node",
});
const model = await import(`data:text/javascript;base64,${Buffer.from(modelBundle.outputFiles[0].contents).toString("base64")}`);
const id = suffix => `00000000-0000-4000-8000-${String(suffix).padStart(12, "0")}`;
const base = (suffix, kind, title, provenance = "worker:unit-test") => ({ contract: "spike/data-view/v1", id: id(suffix), kind, title, provenance });
const mesh = { ...base(1, "mesh", "Returned tetra surface"), coordinate_unit: "mm", vertices: [[0,0,0],[2,0,0],[0,3,4]], triangles: [[0,1,2]] };
const field = { ...base(2, "spatial", "Complex near field"), quantity: "E", coordinate_unit: "mm", value_unit: "V/m", samples: [{ x: 1, y: 2, z: 3, vector_real: [3,4,0], vector_imag: [0,0,12] }] };
const radiation = { ...base(3, "spatial", "Radiation gain pattern", JSON.stringify({ solver: "EMerge/3", display_radius: 1, display_radius_unit: "unitless" })), quantity: "relative gain", coordinate_unit: "unitless", value_unit: "dB", samples: [{ x: 0, y: 0, z: 2, value_real: -3, value_imag: 4 }] };
const line = suffix => ({ ...base(suffix, "line", `Sweep ${suffix}`), x: [1,2], series: [{ name: "S11", values: [-10,-8] }], x_label: "Frequency", y_label: "Magnitude", x_unit: "GHz", y_unit: "dB" });
const polar = { ...base(6, "polar", "Azimuth cut"), x: [0,90,180], series: [{ name: "Gain", values: [1,2,1] }], x_label: "Angle", y_label: "Gain", x_unit: "deg", y_unit: "linear" };
const admitted = model.admitScriptResultViews([mesh, field, radiation, line(4), line(5), polar]);
assert.equal(admitted.length, 6, "all bounded numeric views are admitted by scriptDataViews");
assert.deepEqual(model.spatialChoices(admitted).map(item => item.role), ["radiation", "field", "mesh"], "radiation defaults before fields and mesh");
assert.deepEqual(model.defaultPlotIds(model.plotChoices(admitted)), [id(4), id(5)], "two distinct returned plots are visible by default");
assert.deepEqual(model.spatialBounds(radiation), { x: [0,0], y: [0,0], z: [2,2], unit: "unitless" });
assert.match(model.radiationDisplayNotice(radiation), /display_radius: 1/);
assert.deepEqual(model.probeRows(radiation, 0).slice(-3).map(row => row.label), ["Real", "Imaginary", "Complex magnitude"]);
assert.equal(model.probeRows(radiation, 0).at(-1).value, "5");
const vectorRows = model.probeRows(field, 0);
assert.equal(vectorRows.find(row => row.label === "Complex vector magnitude").value, "13");
assert.equal(model.probeRows(mesh, 2).find(row => row.label === "Z").value, "4");
assert.equal(model.admitScriptResultViews([{ ...radiation, samples: [{ x: 0, y: 0, z: Infinity, value_real: 1, value_imag: 0 }] }]).length, 0, "malformed numeric output remains withheld");
assert.equal(model.plotChoices(admitted).length, 3);
assert.equal(model.plotPresentation(polar).data[0].type, "scatterpolar");

const capMesh = { ...mesh, vertices: Array.from({ length: 10000 }, (_, index) => [index * .000001, index % 2 * .000001, 0]), triangles: Array.from({ length: 10000 }, () => [0,1,2]) };
assert.equal(model.admitScriptResultViews([capMesh]).length, 1, "bounded geometry up to 10,000 vertices and triangles is admitted");
assert.equal(model.admitScriptResultViews([{ ...capMesh, vertices: [...capMesh.vertices, [0,0,0]] }]).length, 0, "oversized vertex data is withheld");
assert.equal(model.admitScriptResultViews([{ ...capMesh, triangles: [...capMesh.triangles, [0,1,2]] }]).length, 0, "oversized connectivity is withheld");
const capField = { ...field, samples: Array.from({ length: 10000 }, () => field.samples[0]) };
assert.equal(model.admitScriptResultViews([capField]).length, 1);
assert.equal(model.admitScriptResultViews([capMesh, capField]).length, 0, "the aggregate numeric cell budget still bounds combined outputs");

const identity = { scene_id: "a".repeat(64), run_id: id(99), coordinate_frame: "emerge-global-xyz", coordinate_unit: "m" };
const modelMesh = { ...mesh, coordinate_unit: "m", vertices: [[-.025,-.01,.001],[.025,-.01,.001],[.025,.01,.004]],
  provenance: JSON.stringify({ ...identity, scene_role: "physical_geometry", phase: "geometry", regions: [{ name: "foil", material: "PEC", triangle_start: 0, triangle_count: 1 }] }) };
const alignedField = { ...field, coordinate_unit: "m", samples: [{ x: .005, y: .007, z: .02, vector_real: [3,4,0], vector_imag: [0,0,12] }], provenance: JSON.stringify(identity) };
const physical = model.physicalGeometry(modelMesh);
assert.equal(physical.phase, "geometry", "a model preview is available before solve");
assert.equal(model.matchingPhysicalGeometry(alignedField, [modelMesh]).view.id, mesh.id);
assert.deepEqual(model.combinedSpatialBounds(alignedField, physical), { x: [-.025,.025], y: [-.01,.01], z: [.001,.02], unit: "m" }, "camera evidence includes the exact model and field coordinates");
assert.equal(model.probeRows(alignedField, 0).find(row => row.label === "Complex vector magnitude").value, "13", "overlay does not change returned field values");
for (const patch of [{ scene_id: "b".repeat(64) }, { run_id: id(100) }, { coordinate_frame: "local" }, { coordinate_unit: "mm" }, { scene_id: "bad" }]) {
  assert.equal(model.matchingPhysicalGeometry({ ...alignedField, provenance: JSON.stringify({ ...identity, ...patch }) }, [modelMesh]), null, "mismatched or malformed scene identity is never overlaid");
}
assert.equal(model.matchingPhysicalGeometry({ ...alignedField, coordinate_unit: "mm" }, [modelMesh]), null);
assert.equal(model.matchingPhysicalGeometry(field, [modelMesh]), null, "legacy data cannot imply alignment");
assert.equal(model.physicalGeometry({ ...modelMesh, provenance: JSON.stringify({ ...JSON.parse(modelMesh.provenance), regions: [{ name: "bad", material: "PEC", triangle_start: 1, triangle_count: 1 }] }) }), null, "invalid region connectivity is withheld");
assert.equal(model.physicalMaterialColor("PEC"), model.physicalMaterialColor("Copper"));
assert.notEqual(model.physicalMaterialColor("PEC"), model.physicalMaterialColor("UnnamedMaterial_1"));
assert.match(model.radiationDisplayNotice({ ...radiation, coordinate_unit: "m", provenance: JSON.stringify({ ...identity, display_radius: .03 }) }, true), /source origin shares.*presentation scale/);

await build({
  entryPoints: [fileURLToPath(new URL("../src/ScriptResultViewport.tsx", import.meta.url))],
  bundle: true, write: false, format: "esm", platform: "browser",
  loader: { ".css": "empty" },
  external: ["react", "react-dom", "lucide-react", "plotly.js-dist-min", "three", "three/examples/jsm/controls/OrbitControls.js"],
});
console.log("script result viewport admission, defaults, probe readouts, and component build passed");
