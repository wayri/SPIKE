import type { FocusEvent, KeyboardEvent } from "react";

const focusGridCell = (table: HTMLTableElement, rowIndex: number, columnIndex: number) => {
  const row = table.tBodies[0]?.rows[rowIndex];
  const control = row?.cells[columnIndex]?.querySelector<HTMLInputElement | HTMLSelectElement>("input:not([type='checkbox']), select, input[type='checkbox']");
  control?.focus();
  if (control instanceof HTMLInputElement && control.type !== "checkbox") control.select();
};

export const onSpreadsheetFocus = (event: FocusEvent<HTMLTableElement>) => {
  const table = event.currentTarget;
  table.querySelectorAll("td.grid-cell-active").forEach(cell => cell.classList.remove("grid-cell-active"));
  (event.target as HTMLElement).closest("td")?.classList.add("grid-cell-active");
};

export const onSpreadsheetKeyDown = (event: KeyboardEvent<HTMLTableElement>) => {
  const control = event.target as HTMLInputElement | HTMLSelectElement;
  const cell = control.closest("td");
  const row = control.closest("tr");
  const table = event.currentTarget;
  if (!cell || !row || !table.tBodies[0]) return;
  const rowIndex = row.sectionRowIndex;
  const columnIndex = cell.cellIndex;
  let nextRow = rowIndex;
  let nextColumn = columnIndex;
  if (event.key === "Enter") nextRow += event.shiftKey ? -1 : 1;
  else if (event.key === "ArrowUp") nextRow -= 1;
  else if (event.key === "ArrowDown") nextRow += 1;
  else if (event.key === "ArrowLeft" && (control instanceof HTMLSelectElement || control.selectionStart === 0)) nextColumn -= 1;
  else if (event.key === "ArrowRight" && (control instanceof HTMLSelectElement || control.selectionEnd === control.value.length)) nextColumn += 1;
  else return;
  if (nextRow < 0 || nextRow >= table.tBodies[0].rows.length || nextColumn < 1 || nextColumn >= row.cells.length) return;
  event.preventDefault();
  focusGridCell(table, nextRow, nextColumn);
};
