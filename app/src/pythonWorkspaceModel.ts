// SPDX-License-Identifier: Apache-2.0
export const PYTHON_CODE_LIMIT = 512_000;
export const PYTHON_TAB_LIMIT = 24;
const STORAGE_KEY = "spike-python-workspace/v2";
const BACKUP_STORAGE_KEY = "spike-python-workspace-backups/v2";
const BACKUP_LIMIT = 5;
const BACKUP_BYTE_LIMIT = 2_000_000;
const SESSION_BYTE_LIMIT = PYTHON_TAB_LIMIT * PYTHON_CODE_LIMIT * 2 + 256_000;
const STRING_LIMIT = 4_096;
const BREAKPOINT_LIMIT = 10_000;

export interface PythonDocument {
  id: string;
  name: string;
  path?: string;
  root?: string;
  sha256?: string;
  code: string;
  savedCode: string;
  breakpoints: number[];
}
export interface PythonWorkspaceSession { documents: PythonDocument[]; activeId: string; root?: string; roots?: string[] }
export interface PythonWorkspaceBackup { id: string; timestamp: number; session: PythonWorkspaceSession }
export interface PythonWorkspacePersistResult { ok: boolean; timestamp?: number; error?: string }
export interface PythonScriptResult {
  contract?: string; status?: string; stdout?: string; stderr?: string;
  return_code?: number; duration_ms?: number; published_result?: unknown;
  ui_actions?: unknown; views?: unknown;
  runtime?: { executable?: string; python_version?: string; emerge_version?: string; optycal_version?: string };
}
export interface PythonDebugFrame { name: string; filename: string; line: number; locals: Record<string, string> }
export interface PythonDebugSnapshot extends PythonScriptResult {
  contract: "spike/python-debug/v1";
  session_id: string;
  status: "starting" | "running" | "paused" | "completed" | "failed" | "stopped";
  line?: number; filename?: string; reason?: string; frames?: PythonDebugFrame[];
  revision?: number; command_ack?: number;
  command_sequence?: number; command_pending?: number;
}
export interface PythonTreeEntry { name: string; path: string; kind: "directory" | "file"; size?: number }
export interface PythonTreeListing { root: string; path: string; entries: PythonTreeEntry[]; truncated?: boolean }

export const pythonPathKey = (path: string) => /^[A-Za-z]:[\\/]/.test(path) ? path.replace(/\\/g, "/").toLowerCase() : path;
export const pythonFileName = (path: string) => path.split(/[\\/]/).filter(Boolean).pop() ?? "untitled.py";
export const pythonAbsolutePath = (root: string, path: string) => /^[A-Za-z]:[\\/]|^\//.test(path) ? path : `${root.replace(/[\\/]$/, "")}/${path.replace(/\\/g, "/")}`;
export const pythonRelativePath = (root: string, path: string) => {
  const prefix = pythonPathKey(root).replace(/\/$/, "");
  const full = pythonPathKey(pythonAbsolutePath(root, path));
  if (full === prefix) return ".";
  if (!full.startsWith(`${prefix}/`)) throw new Error("The script path is outside the selected folder.");
  // Preserve case for case-sensitive filesystems; only comparisons use the normalized key.
  return pythonAbsolutePath(root, path).replace(/\\/g, "/").slice(root.replace(/\\/g, "/").replace(/\/$/, "").length + 1);
};
export const pythonParent = (path: string) => {
  const index = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  if (index === 0) return path.slice(0, 1);
  if (index === 2 && /^[A-Za-z]:/.test(path)) return path.slice(0, 3);
  return index >= 0 ? path.slice(0, index) : ".";
};
export const pythonDirty = (document: PythonDocument) => document.code !== document.savedCode;
export const pythonCodeFits = (code: string) => new TextEncoder().encode(code).byteLength <= PYTHON_CODE_LIMIT;
export const debugFinished = (status?: string) => ["completed", "failed", "stopped"].includes(status ?? "");
export function newPythonDocument(code = "", name = "untitled.py"): PythonDocument {
  return { id: crypto.randomUUID(), name, code, savedCode: code, breakpoints: [] };
}
export function togglePythonBreakpoint(lines: number[], line: number, lineCount: number): number[] {
  if (!Number.isInteger(line) || line < 1 || line > lineCount) return lines;
  return lines.includes(line) ? lines.filter(value => value !== line) : [...lines, line].sort((a, b) => a - b);
}
export function remapPythonBreakpoints(before: string, after: string, breakpoints: number[]): number[] {
  const oldLines = before.split("\n"), newLines = after.split("\n");
  let prefix = 0;
  while (prefix < Math.min(oldLines.length, newLines.length) && oldLines[prefix] === newLines[prefix]) prefix++;
  let suffix = 0;
  while (suffix < Math.min(oldLines.length, newLines.length) - prefix && oldLines[oldLines.length - suffix - 1] === newLines[newLines.length - suffix - 1]) suffix++;
  const delta = newLines.length - oldLines.length;
  return Array.from(new Set(breakpoints.flatMap(line => {
    if (line <= prefix) return [line];
    if (line > oldLines.length - suffix) return [line + delta];
    // Retain edited lines when the number of lines is unchanged; deleted lines lose their breakpoint.
    return delta === 0 && line <= newLines.length ? [line] : [];
  }))).filter(line => line > 0 && line <= newLines.length).sort((a, b) => a - b);
}
export function savedPythonDocument(current: PythonDocument, saved: Pick<PythonDocument, "code" | "path" | "root" | "sha256">): PythonDocument {
  return { ...current, name: saved.path ? pythonFileName(saved.path) : current.name, path: saved.path, root: saved.root, sha256: saved.sha256, savedCode: saved.code };
}
export async function pythonCodeHash(code: string): Promise<string> {
  const bytes = new TextEncoder().encode(code);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash), value => value.toString(16).padStart(2, "0")).join("");
}
const validBoundedString = (value: unknown, allowEmpty = false) => typeof value === "string" && value.length <= STRING_LIMIT && (allowEmpty || value.length > 0) && !/[\u0000-\u001f]/.test(value);
const validId = (value: unknown) => validBoundedString(value) && /^[A-Za-z0-9._:-]+$/.test(value as string);
const validPath = (value: unknown) => validBoundedString(value) && !/[\u0000]/.test(value as string);
const jsonBytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value)).byteLength;

function validatedSession(value: unknown): PythonWorkspaceSession | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Partial<PythonWorkspaceSession>;
  if (!Array.isArray(candidate.documents) || candidate.documents.length > PYTHON_TAB_LIMIT) return null;
  if (candidate.documents.length === 0 ? candidate.activeId !== "" : !validId(candidate.activeId)) return null;
  if (candidate.root !== undefined && !validPath(candidate.root)) return null;
  if (candidate.roots !== undefined && (!Array.isArray(candidate.roots) || candidate.roots.length > PYTHON_TAB_LIMIT || candidate.roots.some(root => !validPath(root)))) return null;
  const ids = new Set<string>();
  const documents: PythonDocument[] = [];
  for (const raw of candidate.documents) {
    if (!raw || typeof raw !== "object") return null;
    const document = raw as Partial<PythonDocument>;
    if (!validId(document.id) || ids.has(document.id as string) || !validBoundedString(document.name)) return null;
    if (document.path !== undefined && !validPath(document.path)) return null;
    if (document.root !== undefined && !validPath(document.root)) return null;
    if (document.sha256 !== undefined && !validBoundedString(document.sha256)) return null;
    if (typeof document.code !== "string" || typeof document.savedCode !== "string" || !pythonCodeFits(document.code) || !pythonCodeFits(document.savedCode)) return null;
    const lineCount = document.code.split("\n").length;
    if (!Array.isArray(document.breakpoints) || document.breakpoints.length > BREAKPOINT_LIMIT || document.breakpoints.some(line => !Number.isInteger(line) || line < 1 || line > lineCount)) return null;
    const breakpoints = [...new Set(document.breakpoints)].sort((a, b) => a - b);
    ids.add(document.id as string);
    documents.push({
      id: document.id as string, name: document.name as string, code: document.code, savedCode: document.savedCode,
      breakpoints, ...(document.path === undefined ? {} : { path: document.path }), ...(document.root === undefined ? {} : { root: document.root }),
      ...(document.sha256 === undefined ? {} : { sha256: document.sha256 }),
    });
  }
  if (documents.length > 0 && !ids.has(candidate.activeId as string)) return null;
  const roots = candidate.roots === undefined ? undefined : [...new Set(candidate.roots)];
  return { documents, activeId: candidate.activeId as string, ...(candidate.root === undefined ? {} : { root: candidate.root }), ...(roots === undefined ? {} : { roots }) };
}

function parseBackups(raw: string | null): PythonWorkspaceBackup[] {
  if (!raw) return [];
  try {
    if (new TextEncoder().encode(raw).byteLength > BACKUP_BYTE_LIMIT) return [];
    const parsed = JSON.parse(raw);
    if (parsed?.version !== 2 || !Array.isArray(parsed.backups) || parsed.backups.length > BACKUP_LIMIT) return [];
    const backups: PythonWorkspaceBackup[] = [];
    for (const item of parsed.backups) {
      const session = validatedSession(item?.session);
      if (!validId(item?.id) || !Number.isSafeInteger(item?.timestamp) || item.timestamp <= 0 || !session) continue;
      backups.push({ id: item.id, timestamp: item.timestamp, session });
    }
    return backups.sort((a, b) => b.timestamp - a.timestamp);
  } catch { return []; }
}

export function listPythonWorkspaceBackups(): PythonWorkspaceBackup[] {
  try { return parseBackups(localStorage.getItem(BACKUP_STORAGE_KEY)); } catch { return []; }
}

function unsavedRecovery(document: PythonDocument): PythonDocument {
  return {
    id: crypto.randomUUID(), name: document.name.replace(/\.py$/i, "") + ".recovered.py", code: document.code,
    savedCode: document.code === "" ? "\n" : "", breakpoints: [...document.breakpoints],
  };
}

export function restorePythonBackupDocument(backup: PythonWorkspaceBackup, documentId: string): PythonDocument | null {
  const session = validatedSession(backup?.session);
  const document = session?.documents.find(item => item.id === documentId);
  return document ? unsavedRecovery(document) : null;
}

function recoveredBackupSession(backup: PythonWorkspaceBackup): PythonWorkspaceSession | null {
  const session = validatedSession(backup.session);
  if (!session) return null;
  const documents = session.documents.map(unsavedRecovery);
  if (!documents.length) return { documents: [], activeId: "", ...(session.root === undefined ? {} : { root: session.root }), ...(session.roots === undefined ? {} : { roots: session.roots }) };
  const activeIndex = session.documents.findIndex(document => document.id === session.activeId);
  return { documents, activeId: documents[Math.max(0, activeIndex)].id, ...(session.root === undefined ? {} : { root: session.root }), ...(session.roots === undefined ? {} : { roots: session.roots }) };
}

export function restorePythonWorkspace(starter: string): PythonWorkspaceSession {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const parsed = raw && new TextEncoder().encode(raw).byteLength <= SESSION_BYTE_LIMIT ? JSON.parse(raw) : null;
    if (parsed?.version === 2) {
      const session = validatedSession(parsed);
      if (session) return session;
    }
  } catch { /* Storage may be disabled; editing remains available. */ }
  try {
    const recovered = listPythonWorkspaceBackups().map(recoveredBackupSession).find((session): session is PythonWorkspaceSession => session !== null);
    if (recovered) return recovered;
  } catch { /* Durable recovery is best-effort. */ }
  const document = newPythonDocument(starter, "welcome.py");
  return { documents: [document], activeId: document.id };
}
export function persistPythonWorkspace(session: PythonWorkspaceSession): PythonWorkspacePersistResult {
  const snapshot = validatedSession(session);
  if (!snapshot) return { ok: false, error: "The Python workspace snapshot is invalid." };
  const timestamp = Date.now();
  const errors: string[] = [];
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 2, ...snapshot })); }
  catch (error) { errors.push(`Session storage failed: ${error instanceof Error ? error.message : String(error)}`); }
  try {
    const previous = listPythonWorkspaceBackups();
    const comparable = (value: PythonWorkspaceSession) => JSON.stringify({ documents: value.documents, root: value.root, roots: value.roots });
    let backups = previous;
    if (!previous.length || comparable(previous[0].session) !== comparable(snapshot)) {
      backups = [{ id: crypto.randomUUID(), timestamp, session: snapshot }, ...previous].slice(0, BACKUP_LIMIT);
      while (backups.length && jsonBytes({ version: 2, backups }) > BACKUP_BYTE_LIMIT) backups.pop();
      if (!backups.length) throw new Error("The workspace snapshot exceeds the durable backup limit.");
      localStorage.setItem(BACKUP_STORAGE_KEY, JSON.stringify({ version: 2, backups }));
    }
  } catch (error) { errors.push(`Recovery backup failed: ${error instanceof Error ? error.message : String(error)}`); }
  return errors.length ? { ok: false, timestamp, error: errors.join(" ") } : { ok: true, timestamp };
}
