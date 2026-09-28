// SPDX-License-Identifier: Apache-2.0

import { normalizeDetachedTracePayload, type DetachedTracePayload } from "./detachedTracePayload";

export type ToolWindowKind = "results" | "probes" | "trace-plots";

export type DetachedToolControl = {
  id: string;
  label: string;
  kind: "select" | "toggle" | "button" | "text";
  value?: string | boolean;
  options?: Array<{ value: string; label: string }>;
  disabled?: boolean;
  title?: string;
};

export type DetachedToolRow = {
  id: string;
  cells: Array<string | number | null>;
  title?: string;
  /** Maps a zero-based cell index to the row action committed by an inline text editor. */
  editActions?: Record<number, string>;
  actions?: DetachedToolRowAction[];
};

export type DetachedToolRowAction = {
  id: string;
  label: string;
  destructive?: boolean;
};

export type DetachedToolSnapshot = {
  kind: ToolWindowKind;
  title: string;
  revision: number;
  status?: string;
  columns: string[];
  rows: DetachedToolRow[];
  controls?: DetachedToolControl[];
  rowActions?: DetachedToolRowAction[];
  emptyMessage?: string;
  trace?: DetachedTracePayload;
};

export type DetachedToolAction = {
  kind: ToolWindowKind;
  type: "ready" | "redock" | "closed" | "control-change" | "row-action";
  controlId?: string;
  rowId?: string;
  actionId?: string;
  value?: string | boolean;
};

export const MAX_DETACHED_ROWS = 2_000;
export const MAX_DETACHED_COLUMNS = 32;
export const MAX_DETACHED_TEXT = 512;
export const MAX_DETACHED_ROW_ID = 768;

const boundedText = (value: unknown, fallback = "") => String(value ?? fallback).slice(0, MAX_DETACHED_TEXT);
const validatedActionId = (value: unknown) => typeof value === "string" && /^[a-zA-Z0-9_.:-]{1,96}$/.test(value) ? value : null;
const transportRowId = (value: unknown) => typeof value === "string" && /^[a-zA-Z0-9_-]{1,768}$/.test(value) ? value : null;

export function encodeDetachedRowId(value: string): string {
  const bytes = new TextEncoder().encode(value.slice(0, MAX_DETACHED_TEXT));
  let binary = "";
  bytes.forEach(byte => { binary += String.fromCharCode(byte); });
  return `row_${btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "")}`;
}

export function decodeDetachedRowId(value: string): string | null {
  if (!/^row_[a-zA-Z0-9_-]{0,683}$/.test(value)) return null;
  try {
    const encoded = value.slice(4).replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "="));
    return new TextDecoder("utf-8", { fatal: true }).decode(Uint8Array.from(binary, character => character.charCodeAt(0)));
  } catch { return null; }
}

export function isToolWindowKind(value: unknown): value is ToolWindowKind {
  return value === "results" || value === "probes" || value === "trace-plots";
}

export function normalizeDetachedToolSnapshot(value: DetachedToolSnapshot): DetachedToolSnapshot {
  const trace = value.kind === "trace-plots" ? normalizeDetachedTracePayload(value.trace) : undefined;
  const columns = Array.isArray(value.columns)
    ? value.columns.slice(0, MAX_DETACHED_COLUMNS).map(item => boundedText(item))
    : [];
  const rows = Array.isArray(value.rows) ? value.rows.slice(0, MAX_DETACHED_ROWS).flatMap(row => {
    const id = transportRowId(row?.id);
    if (!id || !Array.isArray(row?.cells)) return [];
    const editActions = row.editActions && typeof row.editActions === "object"
      ? Object.fromEntries(Object.entries(row.editActions).flatMap(([index, candidateAction]) => {
        const column = Number(index);
        const action = validatedActionId(candidateAction);
        return Number.isInteger(column) && column >= 0 && column < columns.length && action ? [[column, action]] : [];
      }))
      : undefined;
    const actions = Array.isArray(row.actions) ? row.actions.slice(0, 12).flatMap(candidate => {
      const action = validatedActionId(candidate?.id);
      return action ? [{ id: action, label: boundedText(candidate.label), destructive: Boolean(candidate.destructive) }] : [];
    }) : undefined;
    return [{
      id,
      cells: row.cells.slice(0, columns.length).map(cell => cell === null ? null : typeof cell === "number" && Number.isFinite(cell) ? cell : boundedText(cell)),
      ...(row.title ? { title: boundedText(row.title) } : {}),
      ...(editActions && Object.keys(editActions).length ? { editActions } : {}),
      ...(actions?.length ? { actions } : {}),
    }];
  }) : [];
  const controls = Array.isArray(value.controls) ? value.controls.slice(0, 64).flatMap(control => {
    const id = validatedActionId(control?.id);
    if (!id || !["select", "toggle", "button", "text"].includes(control?.kind)) return [];
    return [{
      id,
      label: boundedText(control.label),
      kind: control.kind,
      value: typeof control.value === "boolean" ? control.value : boundedText(control.value),
      disabled: Boolean(control.disabled),
      ...(control.title ? { title: boundedText(control.title) } : {}),
      ...(control.kind === "select" && Array.isArray(control.options) ? {
        options: control.options.slice(0, 128).map(option => ({ value: boundedText(option.value), label: boundedText(option.label) })),
      } : {}),
    } as DetachedToolControl];
  }) : undefined;
  const rowActions = Array.isArray(value.rowActions) ? value.rowActions.slice(0, 12).flatMap(action => {
    const id = validatedActionId(action?.id);
    return id ? [{ id, label: boundedText(action.label), destructive: Boolean(action.destructive) }] : [];
  }) : undefined;
  return {
    kind: value.kind,
    title: boundedText(value.title, value.kind === "probes" ? "Probe table" : value.kind === "trace-plots" ? "Trace graphs" : "Results"),
    revision: Number.isSafeInteger(value.revision) && value.revision >= 0 ? value.revision : 0,
    ...(value.status ? { status: boundedText(value.status) } : {}),
    columns,
    rows,
    ...(controls?.length ? { controls } : {}),
    ...(rowActions?.length ? { rowActions } : {}),
    emptyMessage: boundedText(value.emptyMessage, "No data is available."),
    ...(trace ? { trace } : {}),
  };
}

export function normalizeDetachedToolAction(value: unknown, expectedKind?: ToolWindowKind): DetachedToolAction | null {
  if (!value || typeof value !== "object") return null;
  const source = value as Record<string, unknown>;
  if (!isToolWindowKind(source.kind) || (expectedKind && source.kind !== expectedKind)) return null;
  const type = source.type;
  if (!["ready", "redock", "closed", "control-change", "row-action"].includes(String(type))) return null;
  const action: DetachedToolAction = { kind: source.kind, type: type as DetachedToolAction["type"] };
  for (const key of ["controlId", "rowId", "actionId"] as const) {
    const id = key === "rowId" ? transportRowId(source[key]) : validatedActionId(source[key]);
    if (id) action[key] = id;
  }
  if (typeof source.value === "boolean") action.value = source.value;
  else if (typeof source.value === "string") action.value = boundedText(source.value);
  if (action.type === "control-change" && !action.controlId) return null;
  if (action.type === "row-action" && (!action.rowId || !action.actionId)) return null;
  return action;
}
