// SPDX-License-Identifier: Apache-2.0
/** A new RF setup can reuse the explicit interpreter selected in SPIKE Python. */
export function persistedEnginePython(): string {
  try { return localStorage.getItem("spike-python-interpreter")?.trim() ?? ""; }
  catch { return ""; }
}
