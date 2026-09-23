// SPDX-License-Identifier: Apache-2.0
import type { ParsedStackupLayer } from "./boardParser";

const namedColors: Record<string, string> = {
  black: "#343c40", blue: "#315cb2", green: "#278866", red: "#b34b48",
  white: "#e5e9e6", yellow: "#d7bb53", purple: "#8454a2", matteblack: "#343c40",
};

export function stackupColor(row: ParsedStackupLayer): string {
  const identity = `${row.name} ${row.type}`.toLowerCase();
  if (/mask|silk/.test(identity) && row.color) {
    const color = row.color.trim().toLowerCase().replace(/[\s_-]/g, "");
    if (/^#[0-9a-f]{6}$/.test(color)) return color;
    if (namedColors[color]) return namedColors[color];
  }
  if (/mask/.test(identity)) return "#278866";
  if (/silk/.test(identity)) return "#e5e9e6";
  if (/paste/.test(identity)) return "#aab8c0";
  if (/\.cu\b|copper/.test(identity)) return "#eab559";
  return "#75552c";
}

export function stackupBandHeight(row: ParsedStackupLayer): number {
  return Math.max(6, Math.min(28, 6 + 20 * Math.sqrt(Math.max(0, row.thickness ?? 0) / 0.8)));
}
