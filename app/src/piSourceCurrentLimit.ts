// SPDX-License-Identifier: Apache-2.0
import { parseSpiceNumber } from "./transientWaveform";

/** An empty limit preserves the unlimited source; never serialize invalid numbers. */
export function piSourceCurrentLimitPayload(item: { name: string; currentLimit?: string }): { current_limit_a?: number } {
  if (!item.currentLimit?.trim()) return {};
  const value = parseSpiceNumber(item.currentLimit, `${item.name} current limit`);
  if (!(value > 0)) throw new Error(`${item.name} current limit must be positive, or blank for unlimited.`);
  return { current_limit_a: value };
}
