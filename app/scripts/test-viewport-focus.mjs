import assert from "node:assert/strict";
import { finiteFocusBounds, focusViewBox } from "../src/viewportFocus.ts";

assert.deepEqual(finiteFocusBounds({ minX: 8, minY: 6, maxX: 2, maxY: 4 }), { minX: 2, minY: 4, maxX: 8, maxY: 6 });
assert.equal(finiteFocusBounds({ minX: 0, minY: 0, maxX: Number.NaN, maxY: 1 }), null);
const board = { minX: 0, minY: 0, maxX: 200, maxY: 100 };
const objectFocus = focusViewBox({ minX: 90, minY: 40, maxX: 110, maxY: 50 }, null, board, 2);
assert.deepEqual(objectFocus, { x: 72, y: 31, width: 56, height: 28 }, "object bounds must center and retain a working margin");
const pointFocus = focusViewBox(null, [20, 25], board, 2);
assert.deepEqual(pointFocus, { x: 14, y: 22, width: 12, height: 6 }, "finite selection positions must have a bounded fallback zoom");
assert.equal(focusViewBox(null, [Number.NaN, 1], board, 2), null, "invalid selection coordinates must not move the camera");
const planeFocus = focusViewBox(board, null, board, 2);
assert.ok(planeFocus.width >= 200 && planeFocus.height >= 100, "focusing a board-sized plane must not crop it");
console.log("viewport focus: all assertions passed");
