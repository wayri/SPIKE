// SPDX-License-Identifier: Apache-2.0
import { APP_VERSION, RELEASE_CHANNEL } from "./appVersion";

const ISSUE_URL = "https://github.com/wayri/SPIKE-Main/issues/new";
const WORKSPACES = new Set([
  "Home", "Mesh", "Solve", "PI", "HF / SI", "EM", "EMI", "Thermal", "Probes",
  "Results", "Reports", "Extensions", "Settings",
]);

function platformFamily(userAgent: string): string {
  if (/Windows/i.test(userAgent)) return "Windows";
  if (/Macintosh|Mac OS X/i.test(userAgent)) return "macOS";
  if (/Linux/i.test(userAgent)) return "Linux";
  return "Other";
}

export function bugReportUrl(workspace: string, userAgent: string, desktopShell: boolean): string {
  // Only these fixed application facts are sent in the URL. Never add project,
  // board, net, path, account, log, or solver-result content here.
  const environment = [
    `SPIKE version: ${APP_VERSION}`,
    `Release channel: ${RELEASE_CHANNEL}`,
    `Platform: ${platformFamily(userAgent)}`,
    `Runtime: ${desktopShell ? "Tauri desktop" : "browser preview"}`,
    `Workspace: ${WORKSPACES.has(workspace) ? workspace : "Other"}`,
  ].join("\n");
  const url = new URL(ISSUE_URL);
  url.searchParams.set("template", "bug_report.yml");
  url.searchParams.set("spike-version", APP_VERSION);
  url.searchParams.set("environment", environment);
  return url.toString();
}

export async function openBugReport(workspace: string): Promise<void> {
  const desktopShell = "__TAURI_INTERNALS__" in window;
  const url = bugReportUrl(workspace, navigator.userAgent, desktopShell);
  if (desktopShell) {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
