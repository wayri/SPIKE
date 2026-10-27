// SPDX-License-Identifier: Apache-2.0
import { forwardRef, useId, useImperativeHandle, useRef } from "react";
import { Quaternion, Vector3 } from "three";
import "./buttonStandard.css";
import "./viewportAxisNavigator.css";

export type ViewportRotationAxis = "x" | "y" | "z";
export const NAVIGATOR_ROTATION_STEP = Math.PI / 12;
type Orientation = { x: number; y: number; z: number; w: number };
type RingPoint = { x: number; y: number };
export interface ViewportAxisNavigatorHandle {
  setOrientation: (orientation: Orientation) => void;
}
const AXES = ["x", "y", "z"] as const;
const RADIUS = 53;
const SEGMENTS = 96;

/** Project a world-axis rotation circle into the same 128 px view as the axis helper. */
export function navigatorRingPoints(axis: ViewportRotationAxis, orientation: Orientation): RingPoint[] {
  const inverse = new Quaternion(orientation.x, orientation.y, orientation.z, orientation.w).normalize().invert();
  const point = new Vector3();
  return Array.from({ length: SEGMENTS }, (_, index) => {
    const angle = index * 2 * Math.PI / SEGMENTS, a = Math.cos(angle), b = Math.sin(angle);
    if (axis === "x") point.set(0, a, b);
    else if (axis === "y") point.set(b, 0, a);
    else point.set(a, b, 0);
    point.applyQuaternion(inverse);
    return { x: 64 + RADIUS * point.x, y: 64 - RADIUS * point.y };
  });
}
function ringPath(points: RingPoint[]) {
  return points.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ") + " Z";
}
function ringTangent(points: RingPoint[], x: number, y: number): RingPoint {
  let nearest = 0, distance = Infinity;
  points.forEach((point, index) => {
    const candidate = (point.x - x) ** 2 + (point.y - y) ** 2;
    if (candidate < distance) { nearest = index; distance = candidate; }
  });
  const before = points[(nearest + SEGMENTS - 1) % SEGMENTS], after = points[(nearest + 1) % SEGMENTS];
  const step = 4 * Math.PI / SEGMENTS;
  return { x: (after.x - before.x) / step, y: (after.y - before.y) / step };
}

/** Only the outer ring strokes receive pointer events; axis snapping stays on the canvas. */
const ViewportAxisNavigator = forwardRef<ViewportAxisNavigatorHandle, {
  onRotate: (axis: ViewportRotationAxis, radians: number) => void;
}>(function ViewportAxisNavigator({ onRotate }, ref) {
  const clipId = `axis-ring-${useId().replace(/:/g, "")}`;
  const svg = useRef<SVGSVGElement>(null);
  const orientation = useRef<Orientation>({ x: 0, y: 0, z: 0, w: 1 });
  const rings = useRef(AXES.map(axis => navigatorRingPoints(axis, orientation.current)));
  const drag = useRef<{ pointer: number; axis: ViewportRotationAxis; x: number; y: number; moved: boolean } | null>(null);
  const skipClick = useRef(false);
  useImperativeHandle(ref, () => ({ setOrientation(value) {
    if (![value.x, value.y, value.z, value.w].every(Number.isFinite)) return;
    const previous = orientation.current;
    if (previous.x === value.x && previous.y === value.y && previous.z === value.z && previous.w === value.w) return;
    orientation.current = { x: value.x, y: value.y, z: value.z, w: value.w };
    rings.current = AXES.map(axis => navigatorRingPoints(axis, value));
    AXES.forEach((axis, index) => {
      svg.current?.querySelectorAll(`[data-axis="${axis}"] path`).forEach(path => path.setAttribute("d", ringPath(rings.current[index])));
    });
  } }), []);
  return <aside className="viewport-axis-navigator" aria-label="Axis navigator">
    <svg ref={svg} className="viewport-axis-navigator__rotation" viewBox="0 0 128 128" width="128" height="128"
      role="group" aria-label="Camera rotation rings">
      <defs><clipPath id={clipId}><path clipRule="evenodd" d="M0 0H128V128H0Z M104 64A40 40 0 1 0 24 64A40 40 0 1 0 104 64Z" /></clipPath></defs>
      <g clipPath={`url(#${clipId})`}>
      {AXES.map((axis, index) => <g key={axis} role="button" tabIndex={0}
        className="viewport-axis-navigator__ring" data-axis={axis}
        aria-label={`Rotate camera about ${axis.toUpperCase()} axis`}
        onPointerDown={event => {
          event.stopPropagation();
          if (event.button !== 0 || drag.current) return;
          skipClick.current = false;
          drag.current = { pointer: event.pointerId, axis, x: event.clientX, y: event.clientY, moved: false };
          event.currentTarget.focus();
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={event => {
          const current = drag.current;
          if (!current || current.pointer !== event.pointerId || current.axis !== axis) return;
          event.stopPropagation();
          const dx = event.clientX - current.x, dy = event.clientY - current.y;
          if (!current.moved && Math.hypot(dx, dy) < 3) return;
          const bounds = svg.current?.getBoundingClientRect();
          if (!bounds || !bounds.width || !bounds.height) return;
          const scaleX = 128 / bounds.width, scaleY = 128 / bounds.height;
          const tangent = ringTangent(rings.current[index], (current.x - bounds.left) * scaleX, (current.y - bounds.top) * scaleY);
          const length = Math.hypot(tangent.x, tangent.y);
          current.moved = true;
          skipClick.current = true;
          current.x = event.clientX; current.y = event.clientY;
          // Orbiting the camera turns the world rings in the opposite direction.
          if (length > 1) onRotate(axis, -(dx * scaleX * tangent.x + dy * scaleY * tangent.y) / (length * Math.max(18, length)));
        }}
        onPointerUp={event => {
          event.stopPropagation();
          if (drag.current?.pointer === event.pointerId) drag.current = null;
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={event => { event.stopPropagation(); drag.current = null; skipClick.current = true; }}
        onLostPointerCapture={event => { event.stopPropagation(); drag.current = null; }}
        onClick={event => {
          event.stopPropagation();
          if (skipClick.current) { skipClick.current = false; return; }
          onRotate(axis, NAVIGATOR_ROTATION_STEP * (event.shiftKey ? -1 : 1));
        }}
        onDoubleClick={event => event.stopPropagation()}
        onContextMenu={event => { event.preventDefault(); event.stopPropagation(); }}
        onKeyDown={event => {
          event.stopPropagation();
          if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter", " ", "+", "-", "="].includes(event.key)) return;
          event.preventDefault();
          skipClick.current = false;
          const reverse = ["ArrowLeft", "ArrowDown", "-"].includes(event.key) || (event.shiftKey && ["Enter", " "].includes(event.key));
          onRotate(axis, NAVIGATOR_ROTATION_STEP * (reverse ? -1 : 1));
        }}>
        <title>{`Rotate about ${axis.toUpperCase()}: drag ring, click +15 degrees, Shift-click -15 degrees, or use arrow / +/- keys`}</title>
        <path className="viewport-axis-navigator__ring-edge" d={ringPath(rings.current[index])} />
        <path className="viewport-axis-navigator__ring-line" d={ringPath(rings.current[index])} />
        <path className="viewport-axis-navigator__ring-hit" d={ringPath(rings.current[index])} />
      </g>)}
      </g>
    </svg>
  </aside>;
});
export default ViewportAxisNavigator;
