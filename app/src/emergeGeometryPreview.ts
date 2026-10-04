// SPDX-License-Identifier: Apache-2.0
/** Prepare the bundled bridge's mesh-only execution without changing the editable source. */
export function emergeGeometryPreview(code: string): string | null {
  if (!/bridge\s*=.*upstream-emerge.*bridge\.py/.test(code) || !/^execution_options\s*=.*$/m.test(code)) return null;
  const call = /^runpy\.run_path\(str\(bridge\)\)\[['"]run_example['"]\]\s*\(/m;
  if (!call.test(code)) return null;
  return code.replace(call, "execution_options['geometry_only'] = True\n$&");
}
