import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const styles = readFileSync(resolve(scriptDir, "../src/styles.css"), "utf8");

const requiredRules = [
  [/:root\s*\{[\s\S]*?color-scheme:\s*var\(--spike-table-scheme,\s*dark\)\s*;/, "theme-aware root color scheme with dark fallback"],
  [/select\s*\{\s*color-scheme:\s*var\(--spike-table-scheme,\s*dark\)\s*;\s*\}/, "theme-aware native select color scheme"],
  [/select option,\s*select optgroup\s*\{[^}]*color:\s*var\(--spike-text,\s*#[0-9a-f]{6}\)\s*;[^}]*background-color:\s*var\(--spike-surface-panel,\s*#[0-9a-f]{6}\)\s*;/i, "tokenized option popup foreground and background"],
  [/select option:disabled\s*\{[^}]*color:\s*var\(--spike-text-muted,\s*#[0-9a-f]{6}\)\s*;/i, "tokenized disabled option contrast"],
];

for (const [pattern, description] of requiredRules) {
  if (!pattern.test(styles)) {
    throw new Error(`Missing ${description} rule in styles.css`);
  }
}

console.log("Native select popup contrast contract passed.");
