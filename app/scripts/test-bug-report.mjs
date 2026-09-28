// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const options = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 };
const version = ts.transpileModule(readFileSync(new URL("../src/appVersion.ts", import.meta.url), "utf8"), { compilerOptions: options }).outputText;
const versionUrl = `data:text/javascript;base64,${Buffer.from(version).toString("base64")}`;
const { APP_VERSION } = await import(versionUrl);
const source = ts.transpileModule(readFileSync(new URL("../src/bugReport.ts", import.meta.url), "utf8"), { compilerOptions: options }).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source.replace('from "./appVersion";', `from "${versionUrl}";`)).toString("base64")}`;
const { bugReportUrl } = await import(moduleUrl);

const url = new URL(bugReportUrl("PI", "Windows NT 10.0 private-host /Users/alice", true));
assert.equal(url.origin, "https://github.com");
assert.equal(url.pathname, "/wayri/SPIKE-Main/issues/new");
assert.equal(url.searchParams.get("template"), "bug_report.yml");
assert.equal(url.searchParams.get("spike-version"), APP_VERSION);
assert.match(url.searchParams.get("environment"), /Platform: Windows/);
assert.match(url.searchParams.get("environment"), /Workspace: PI/);
assert.doesNotMatch(url.toString(), /alice|private-host/);
assert.match(new URL(bugReportUrl("EM", "unknown", false)).searchParams.get("environment"), /Workspace: EM/);
assert.match(new URL(bugReportUrl("EMI", "unknown", false)).searchParams.get("environment"), /Workspace: EMI/);
assert.match(new URL(bugReportUrl("C:\\private\\board.kicad_pcb", "unknown", false)).searchParams.get("environment"), /Workspace: Other/);
console.log("Bug report URL metadata allowlist passed");
