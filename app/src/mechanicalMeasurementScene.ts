// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

export type MechanicalMeasurement = {
  pointA: readonly [number, number, number];
  pointB: readonly [number, number, number];
};

export type AssemblyWorldTransform = { centerX: number; centerY: number; scale: number };

export function assemblyMeasurementWorldPoint(point: readonly [number, number, number], transform: AssemblyWorldTransform): [number, number, number] {
  return [
    (point[0] - transform.centerX) * transform.scale,
    (transform.centerY - point[1]) * transform.scale,
    point[2] * transform.scale,
  ];
}

export function buildMechanicalMeasurementScene(measurement: MechanicalMeasurement, transform: AssemblyWorldTransform) {
  const group = new THREE.Group();
  group.name = "mechanical-measurement-assembly-frame-mm";
  group.scale.set(transform.scale, -transform.scale, transform.scale);
  group.position.set(-transform.centerX * transform.scale, transform.centerY * transform.scale, 0);
  const pointA = new THREE.Vector3(...measurement.pointA);
  const pointB = new THREE.Vector3(...measurement.pointB);
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([pointA, pointB]),
    new THREE.LineBasicMaterial({ color: 0xffd35a, depthTest: false, transparent: true, opacity: .96 }),
  );
  line.renderOrder = 410;
  line.userData.mechanicalMeasurement = true;
  group.add(line);
  const radius = Math.max(.45, .8 / Math.max(transform.scale, Number.EPSILON));
  for (const [index, point] of [pointA, pointB].entries()) {
    const marker = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 16, 10),
      new THREE.MeshBasicMaterial({ color: index === 0 ? 0x63e6ff : 0xff8e5a, depthTest: false }),
    );
    marker.position.copy(point);
    marker.renderOrder = 411;
    marker.userData.mechanicalMeasurementEndpoint = index === 0 ? "A" : "B";
    group.add(marker);
  }
  return group;
}
