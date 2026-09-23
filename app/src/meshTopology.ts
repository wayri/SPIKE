import type { MeshCell } from "./analysisResults";

export function meshCellEdgeIndexes(cell: MeshCell): [number, number][] {
  const vertexCount = cell.vertices_mm.length;
  if (vertexCount < 2) return [];
  const isPrism = cell.topology?.startsWith("prism")
    || cell.kind === "volume" && cell.topology !== "hex8_barrel" && cell.source_kind !== "via";
  if (isPrism && vertexCount >= 6 && vertexCount % 2 === 0) {
    const faceVertices = vertexCount / 2;
    return [
      ...Array.from({ length: faceVertices }, (_, index) => [index, (index + 1) % faceVertices] as [number, number]),
      ...Array.from({ length: faceVertices }, (_, index) => [index + faceVertices, (index + 1) % faceVertices + faceVertices] as [number, number]),
      ...Array.from({ length: faceVertices }, (_, index) => [index, index + faceVertices] as [number, number]),
    ];
  }
  if (cell.kind === "volume" && vertexCount === 8) {
    return [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
  }
  return Array.from({ length: vertexCount }, (_, index) => [index, (index + 1) % vertexCount] as [number, number]);
}

export function meshCellFaceVertices(cell: MeshCell) {
  if (cell.kind === "volume" && cell.vertices_mm.length >= 6 && cell.vertices_mm.length % 2 === 0) {
    return cell.vertices_mm.slice(0, cell.vertices_mm.length / 2);
  }
  return cell.vertices_mm;
}
