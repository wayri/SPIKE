// SPDX-License-Identifier: Apache-2.0
import type { KeyboardEvent } from "react";

const fields = "input:not([type='hidden']), select, textarea";
const editable = (element: Element): element is HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement =>
  element.matches(fields) && !element.matches(":disabled, [readonly], [tabindex='-1']") && element.getClientRects().length > 0;

/** Normal arrows edit text/numbers/selects. Explicit Alt+arrows navigate the table. */
export function onSpreadsheetKeyDown(event: KeyboardEvent<HTMLTableElement>) {
  if (event.defaultPrevented || event.nativeEvent.isComposing || event.ctrlKey || event.metaKey) return;
  const target = event.target;
  const table = event.currentTarget;
  if (!(target instanceof HTMLElement) || target.closest("table") !== table || !editable(target)) return;
  const enter = event.key === "Enter" && !event.altKey;
  const direction = event.altKey ? ({ ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] } as Record<string, number[]>)[event.key]
    : enter ? [event.shiftKey ? -1 : 1, 0] : undefined;
  if (!direction || (enter && (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement))) return;
  const cell = target.closest<HTMLTableCellElement>("td, th");
  const row = cell?.parentElement as HTMLTableRowElement | null;
  if (!cell || !row || row.parentElement?.tagName !== "TBODY") return;
  const rows = Array.from(table.tBodies).flatMap(body => Array.from(body.rows));
  const controls = (candidate: HTMLTableCellElement) => Array.from(candidate.querySelectorAll(fields)).filter(field => field.closest("table") === table && editable(field));
  const column = Array.from(row.cells).slice(0, cell.cellIndex).reduce((sum, item) => sum + item.colSpan, 0);
  let next: Element | undefined;
  if (direction[0]) {
    for (let r = rows.indexOf(row) + direction[0]; r >= 0 && r < rows.length; r += direction[0]) {
      let offset = 0;
      const candidate = Array.from(rows[r].cells).find(item => { const matches = offset === column && item.colSpan === cell.colSpan; offset += item.colSpan; return matches; });
      if (candidate) next = controls(candidate)[0];
      if (next) break;
    }
  } else {
    for (let c = cell.cellIndex + direction[1]; c >= 0 && c < row.cells.length; c += direction[1]) {
      const candidates = controls(row.cells[c]);
      next = direction[1] > 0 ? candidates[0] : candidates[candidates.length - 1];
      if (next) break;
    }
  }
  // Boundaries must not submit a form or trigger browser Alt+Left/Right history.
  event.preventDefault();
  if (next instanceof HTMLElement) {
    next.focus();
    if (next instanceof HTMLInputElement && ["text", "search", "tel", "url", "password"].includes(next.type)) next.select();
  }
}
