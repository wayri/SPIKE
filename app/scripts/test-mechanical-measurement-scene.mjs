// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { Vector3 } from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { assemblyMeasurementWorldPoint, buildMechanicalMeasurementScene } = await importTestTypescript("mechanicalMeasurementScene");
const transform = { centerX: 10, centerY: 20, scale: 2.5 };
const measurement = { pointA: [12, 17, 3], pointB: [-2, 25, -4] };
assert.deepEqual(assemblyMeasurementWorldPoint(measurement.pointA, transform), [5, 7.5, 7.5]);
assert.deepEqual(assemblyMeasurementWorldPoint(measurement.pointB, transform), [-30, -12.5, -10]);

const scene = buildMechanicalMeasurementScene(measurement, transform);
scene.updateMatrixWorld(true);
const endpoints = scene.children.filter(child => child.userData.mechanicalMeasurementEndpoint);
assert.equal(endpoints.length, 2, "both retained measurement endpoints are rendered");
assert.deepEqual(endpoints.map(endpoint => endpoint.getWorldPosition(new Vector3()).toArray()), [[5, 7.5, 7.5], [-30, -12.5, -10]],
  "endpoint markers use the same centered, Y-flipped assembly-to-world transform as MCAD parts");
const line = scene.children.find(child => child.userData.mechanicalMeasurement);
const positions = Array.from(line.geometry.getAttribute("position").array);
assert.deepEqual(positions, [...measurement.pointA, ...measurement.pointB], "line vertices remain in canonical assembly millimetres inside the transformed frame");

scene.traverse(object => {
  object.geometry?.dispose?.();
  const materials = object.material ? Array.isArray(object.material) ? object.material : [object.material] : [];
  materials.forEach(material => material.dispose());
});
console.log("Mechanical measurement endpoint transform and retained 3D scene passed");
