// SPDX-License-Identifier: Apache-2.0
import type { ZoneDisplayMode } from "./zoneDisplay";
export const isZoneDisplayMode = (value: unknown): value is ZoneDisplayMode => value === "filled" || value === "transparent" || value === "outline";
export const normalizeZoneDisplay = (value: unknown): ZoneDisplayMode => isZoneDisplayMode(value) ? value : "filled";
export function normalizeAssemblyZoneDisplay(value: unknown): Record<string, ZoneDisplayMode> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value).filter((row): row is [string, ZoneDisplayMode] => isZoneDisplayMode(row[1]))) : {};
}
