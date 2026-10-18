// SPDX-License-Identifier: Apache-2.0
// Presentation admission only; numerical state remains in the native worker.
export type CavityRequest = { n: number; reynolds: number };
export type CavityResult = { status: "converged" | "failed_to_converge"; settings: CavityRequest;
  diagnostics: Record<string, number>; fields: null | Record<string, number[]> };
const row = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
export function admitCavityResult(value: unknown, request: CavityRequest): CavityResult {
  const result = row(value), settings = row(result.settings), diagnostics = row(result.diagnostics);
  if (result.schema !== "spike-native-cavity-v1" || result.model_status !== "experimental" || result.production_qualified !== false ||
      !["converged", "failed_to_converge"].includes(String(result.status)) || settings.n !== request.n || settings.reynolds !== request.reynolds)
    throw new Error("Native CFD returned an incompatible result or request identity.");
  const admitted: Record<string, number> = {};
  for (const key of ["steps", "time", "dt", "divergence_linf", "steady_rate_linf", "poisson_residual_linf"]) {
    const number = diagnostics[key];
    if (typeof number !== "number" || !Number.isFinite(number) || number < 0) throw new Error("Native CFD returned invalid diagnostics.");
    admitted[key] = number;
  }
  if (!Number.isInteger(admitted.steps) || admitted.steps < 1 || admitted.dt <= 0) throw new Error("Native CFD returned invalid step diagnostics.");
  if (result.status === "failed_to_converge") {
    if (result.fields !== null) throw new Error("Unconverged native CFD fields cannot be displayed.");
    return { status: "failed_to_converge", settings: request, diagnostics: admitted, fields: null };
  }
  if (admitted.divergence_linf > 1e-7 || admitted.steady_rate_linf >= 1e-7 || admitted.poisson_residual_linf > 4e-9)
    throw new Error("Native CFD convergence diagnostics failed admission.");
  const fields = row(result.fields), arrays: Record<string, number[]> = {}, count = request.n ** 2;
  for (const key of ["x_m", "y_m", "u_m_s", "v_m_s", "pressure_pa"]) {
    const values = fields[key];
    if (!Array.isArray(values) || values.length !== count || values.some(x => typeof x !== "number" || !Number.isFinite(x)))
      throw new Error("Native CFD returned malformed or nonfinite fields.");
    arrays[key] = values.slice();
  }
  for (let j = 0; j < request.n; j++) for (let i = 0; i < request.n; i++) {
    const k = j * request.n + i;
    if (arrays.x_m[k] !== arrays.x_m[i] || arrays.y_m[k] !== arrays.y_m[j * request.n] ||
        (i > 0 && arrays.x_m[k] <= arrays.x_m[k - 1]) || (j > 0 && arrays.y_m[k] <= arrays.y_m[k - request.n]))
      throw new Error("Native CFD coordinates are not an ordered Cartesian grid.");
  }
  return { status: "converged", settings: request, diagnostics: admitted, fields: arrays };
}
export function cavityHeatmap(result: CavityResult, field: "speed" | "pressure") {
  if (!result.fields || result.status !== "converged") throw new Error("No converged native CFD field.");
  const f = result.fields, n = result.settings.n;
  const values = field === "pressure" ? f.pressure_pa : f.u_m_s.map((u, i) => Math.hypot(u, f.v_m_s[i]));
  if (values.some(v => !Number.isFinite(v))) throw new Error("Native CFD display values overflowed.");
  return [{ type: "heatmap", x: f.x_m.slice(0, n), y: Array.from({ length: n }, (_, j) => f.y_m[j * n]),
    z: Array.from({ length: n }, (_, j) => values.slice(j * n, (j + 1) * n)), colorscale: "Viridis",
    colorbar: { title: { text: field === "pressure" ? "Pa" : "m/s" } },
    hovertemplate: "x=%{x:.4g} m<br>y=%{y:.4g} m<br>value=%{z:.4g}<extra></extra>" }];
}
