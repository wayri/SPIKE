// SPDX-License-Identifier: Apache-2.0

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const runnerName = "test:ui-stability";
const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const appDirectory = resolve(scriptDirectory, "..");
const repositoryDirectory = resolve(appDirectory, "..");
const localDirectory = resolve(repositoryDirectory, ".local");
const argumentsList = process.argv.slice(2);
const dryRun = argumentsList.includes("--dry-run");
const timeoutArgument = argumentsList.find(value => value.startsWith("--timeout-ms="));
const reportArgument = argumentsList.find(value => value.startsWith("--report="));
const requestedSuites = new Set(argumentsList.filter(value => value.startsWith("--suite=")).map(value => value.slice("--suite=".length)));
const timeoutMs = Number(timeoutArgument?.slice("--timeout-ms=".length) ?? process.env.SPIKE_UI_TEST_TIMEOUT_MS ?? 300_000);
const reportPath = resolve(repositoryDirectory, reportArgument?.slice("--report=".length) ?? ".local/ui-stability-tests.json");

if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1_000) {
  throw new Error("UI stability timeout must be an integer of at least 1000 ms");
}
if (!reportPath.startsWith(`${repositoryDirectory}\\`) && !reportPath.startsWith(`${repositoryDirectory}/`)) {
  throw new Error("UI stability report must remain inside the repository");
}

const packageMetadata = JSON.parse(readFileSync(resolve(appDirectory, "package.json"), "utf8"));
const suites = Object.entries(packageMetadata.scripts)
  .filter(([name]) => name.startsWith("test:") && name !== runnerName && (requestedSuites.size === 0 || requestedSuites.has(name)))
  .map(([name, declaredScript]) => ({ name, declaredScript }));
const missingSuites = [...requestedSuites].filter(name => !suites.some(suite => suite.name === name));
if (missingSuites.length > 0) throw new Error(`Unknown UI stability suite(s): ${missingSuites.join(", ")}`);
const results = [];
const firstSuiteByCommand = new Map();
const startedAt = new Date();

function lines(value) {
  return String(value ?? "").replaceAll("\r\n", "\n").split("\n").filter(Boolean);
}

function summary() {
  const executed = results.filter(result => result.status !== "skipped_duplicate");
  return {
    suiteCount: suites.length,
    completedCount: results.length,
    executedCount: executed.length,
    duplicateCount: results.length - executed.length,
    passedCount: executed.filter(result => result.status === "passed").length,
    failedCount: executed.filter(result => result.status === "failed").length,
    timedOutCount: executed.filter(result => result.timedOut).length,
    plannedCount: executed.filter(result => result.status === "planned").length,
  };
}

function writeCheckpoint(final = false) {
  const now = new Date();
  mkdirSync(dirname(reportPath), { recursive: true });
  writeFileSync(reportPath, `${JSON.stringify({
    schemaVersion: 1,
    scope: "Every app/package.json test:* suite except test:ui-stability, run sequentially",
    startedAtUtc: startedAt.toISOString(),
    lastUpdatedAtUtc: now.toISOString(),
    ...(final ? { finishedAtUtc: now.toISOString(), durationSeconds: (now - startedAt) / 1000 } : {}),
    timeoutMs,
    dryRun,
    ...summary(),
    limitations: [
      "These Node-based static and behavioral regression suites do not establish native Tauri or WebView interaction behavior.",
      "The suites do not provide installed-package, screenshot, supported-window-size, or accessibility-tool acceptance evidence.",
      "Passing presentation suites do not validate solver physics or numerical accuracy.",
      "Only identical complete package commands are deduplicated; compound commands retain package order and shell short-circuit behavior."
    ],
    results,
  }, null, 2)}\n`);
}

function runNpmSuite(name) {
  const options = {
    cwd: appDirectory,
    encoding: "utf8",
    windowsHide: true,
    timeout: timeoutMs,
    killSignal: "SIGTERM",
    maxBuffer: 64 * 1024 * 1024,
  };
  return process.platform === "win32"
    ? spawnSync(process.env.ComSpec ?? "cmd.exe", ["/d", "/s", "/c", "npm.cmd", "run", name], options)
    : spawnSync("npm", ["run", name], options);
}

for (const suite of suites) {
  const duplicateOf = firstSuiteByCommand.get(suite.declaredScript);
  if (duplicateOf) {
    results.push({ ...suite, command: `npm run ${suite.name}`, status: "skipped_duplicate", duplicateOf });
  } else if (dryRun) {
    firstSuiteByCommand.set(suite.declaredScript, suite.name);
    results.push({ ...suite, command: `npm run ${suite.name}`, status: "planned" });
  } else {
    firstSuiteByCommand.set(suite.declaredScript, suite.name);
    const suiteStartedAt = new Date();
    const child = runNpmSuite(suite.name);
    const stdout = lines(child.stdout);
    const stderr = lines(child.stderr);
    const combined = [...stdout, ...stderr];
    const timedOut = child.error?.code === "ETIMEDOUT";
    const exitCode = child.status ?? 1;
    results.push({
      ...suite,
      command: `npm run ${suite.name}`,
      startedAtUtc: suiteStartedAt.toISOString(),
      durationSeconds: (new Date() - suiteStartedAt) / 1000,
      exitCode,
      signal: child.signal ?? null,
      timedOut,
      status: exitCode === 0 && !child.error ? "passed" : "failed",
      spawnError: child.error?.message ?? null,
      failureLines: exitCode === 0 && !child.error ? [] : combined.filter(line => /fail|error|assert|exception|not found|cannot|missing|timed? out|stale/i.test(line)).slice(-60),
      outputTail: combined.slice(-(exitCode === 0 && !child.error ? 25 : 160)),
      stdoutLineCount: stdout.length,
      stderrLineCount: stderr.length,
    });
  }
  writeCheckpoint(false);
  const current = results.at(-1);
  console.log(`[${results.length}/${suites.length}] ${suite.name}: ${current.status}${current.durationSeconds === undefined ? "" : ` (${current.durationSeconds.toFixed(2)}s)`}`);
}

writeCheckpoint(true);
const totals = summary();
console.log(dryRun
  ? `UI stability dry run: ${totals.plannedCount} suites planned, ${totals.duplicateCount} duplicate commands skipped. Report: ${reportPath}`
  : `UI stability: ${totals.passedCount} passed, ${totals.failedCount} failed, ${totals.duplicateCount} duplicate commands skipped. Report: ${reportPath}`);
if (!dryRun && totals.failedCount > 0) process.exitCode = 1;
