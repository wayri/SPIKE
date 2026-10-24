// SPDX-License-Identifier: Apache-2.0
/** Geometry measurements in the right-handed assembly frame, in millimetres. */
export type MeasurementPoint = readonly [number, number, number];
export interface MechanicalMeasurementPoints { pointA: MeasurementPoint; pointB: MeasurementPoint }
export interface MechanicalMeasurement extends MechanicalMeasurementPoints {
  frame: "assembly";
  units: "mm";
  delta: MeasurementPoint;
  distance: number;
}
export function measureMechanicalPoints(pointA: MeasurementPoint, pointB: MeasurementPoint): MechanicalMeasurement {
  if (pointA.length !== 3 || pointB.length !== 3 || ![...pointA, ...pointB].every(Number.isFinite)) {
    throw new Error("Enter finite X, Y and Z coordinates for both points.");
  }
  const delta = pointB.map((value, axis) => value - pointA[axis]) as unknown as MeasurementPoint;
  const distance = Math.hypot(...delta);
  if (!delta.every(Number.isFinite) || !Number.isFinite(distance)) throw new Error("Coordinates exceed the supported measurement range.");
  return {frame: "assembly", units: "mm", pointA: [...pointA], pointB: [...pointB], delta, distance};
}
export function parseMeasurementPoint(values: readonly string[]): MeasurementPoint | null {
  if (values.length !== 3 || values.some(value => !value.trim())) return null;
  const numbers = values.map(Number);
  return numbers.every(Number.isFinite) ? numbers as unknown as MeasurementPoint : null;
}
export function mechanicalMeasurementCsv(measurement: MechanicalMeasurement): string {
  const checked = measureMechanicalPoints(measurement.pointA, measurement.pointB);
  return "frame,units,ax,ay,az,bx,by,bz,delta_x,delta_y,delta_z,distance\r\n" +
    [checked.frame, checked.units, ...checked.pointA, ...checked.pointB, ...checked.delta, checked.distance].join(",") + "\r\n";
}
