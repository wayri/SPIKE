// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { importTestTypescript } from "./import-test-typescript.mjs";

globalThis.crypto ??= webcrypto;
const sessions = new Map(), durable = new Map();
globalThis.sessionStorage = { getItem: key => sessions.get(key) ?? null, setItem: (key, value) => sessions.set(key, value) };
globalThis.localStorage = { getItem: key => durable.get(key) ?? null, setItem: (key, value) => durable.set(key, value) };
const model = await importTestTypescript("pythonWorkspaceModel");
const document = (id, code, extra = {}) => ({ id, name: `${id}.py`, code, savedCode: code, breakpoints: [], ...extra });
const session = (id, code, extra = {}) => ({ documents: [document(id, code)], activeId: id, ...extra });

const first = session("one", "print(1)", { root: "C:/scripts", roots: ["C:/scripts"] });
assert.equal(model.persistPythonWorkspace(first).ok, true);
sessions.clear();
const recovered = model.restorePythonWorkspace("starter");
assert.equal(recovered.documents[0].code, "print(1)", "durable backup survives a session restart");
assert.notEqual(recovered.documents[0].id, "one");
assert.equal(recovered.documents[0].path, undefined);
assert.equal(recovered.documents[0].sha256, undefined);
assert.equal(model.pythonDirty(recovered.documents[0]), true, "automatic recovery opens an unsaved copy");
assert.deepEqual(recovered.roots, ["C:/scripts"]);

sessions.set("spike-python-workspace/v2", "{broken");
assert.equal(model.restorePythonWorkspace("starter").documents[0].code, "print(1)", "corrupt session falls back to durable recovery");
const listed = model.listPythonWorkspaceBackups();
const copy = model.restorePythonBackupDocument(listed[0], "one");
assert.equal(copy.code, "print(1)"); assert.notEqual(copy.id, "one"); assert.equal(copy.path, undefined); assert.equal(model.pythonDirty(copy), true);

const activeOnly = { ...first, activeId: "two", documents: [document("one", "print(1)"), document("two", "print(2)")] };
model.persistPythonWorkspace(activeOnly);
const count = model.listPythonWorkspaceBackups().length;
model.persistPythonWorkspace({ ...activeOnly, activeId: "one" });
assert.equal(model.listPythonWorkspaceBackups().length, count, "active-tab-only changes are deduplicated");
for (let index = 0; index < 8; index++) model.persistPythonWorkspace(session(`v${index}`, `print(${index})`));
assert.equal(model.listPythonWorkspaceBackups().length, 5, "durable generations are bounded");

const beforeQuota = model.listPythonWorkspaceBackups();
globalThis.localStorage.setItem = () => { throw new Error("quota"); };
const failed = model.persistPythonWorkspace(session("quota", "changed"));
assert.equal(failed.ok, false); assert.match(failed.error, /quota/);
assert.deepEqual(model.listPythonWorkspaceBackups(), beforeQuota, "quota failure retains the last valid generations");
globalThis.localStorage.setItem = (key, value) => durable.set(key, value);

const storageKey = [...durable.keys()][0];
durable.set(storageKey, JSON.stringify({ version: 2, backups: [{ id: "bad", timestamp: Date.now(), session: session("bad", "x", { roots: [42] }) }] }));
assert.deepEqual(model.listPythonWorkspaceBackups(), [], "malformed backup sessions are rejected");
sessions.set("spike-python-workspace/v2", JSON.stringify({ version: 2, ...session("bad-sha", "x", { documents: [document("bad-sha", "x", { sha256: "x".repeat(5_000), breakpoints: [0] })] }) }));
assert.equal(model.restorePythonWorkspace("starter").documents[0].name, "welcome.py", "malformed session data is not partially trusted");

durable.clear(); sessions.clear();
const saving = { documents: [document("concurrent", "edited", { savedCode: "on disk" })], activeId: "concurrent" };
assert.equal(model.persistPythonWorkspace(saving).ok, true);
saving.documents[0].code = "after";
saving.documents[0].savedCode = "after save completed";
const durableSnapshot = model.listPythonWorkspaceBackups()[0].session.documents[0];
assert.equal(durableSnapshot.code, "edited"); assert.equal(durableSnapshot.savedCode, "on disk", "backup captures a consistent save-time snapshot");

durable.clear(); sessions.clear();
const empty = { documents: [], activeId: "", root: "C:/scripts", roots: ["C:/scripts"] };
assert.equal(model.persistPythonWorkspace(empty).ok, true, "closing the last tab is a valid workspace state");
assert.deepEqual(model.restorePythonWorkspace("starter"), empty, "session restore keeps all tabs closed");
sessions.clear();
assert.deepEqual(model.restorePythonWorkspace("starter"), empty, "durable recovery does not resurrect closed tabs");
console.log("Python workspace durable recovery, validation, quota retention, bounds, dedupe and unsaved-copy restore passed");
