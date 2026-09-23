import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const styles = readFileSync(resolve(scriptDir, "../src/styles.css"), "utf8");

const requiredRules = [
  [/:root\s*\{[\s\S]*?color-scheme:\s*dark\s*;/, "root dark color scheme"],
  [/select\s*\{\s*color-scheme:\s*dark\s*;\s*\}/, "native select dark color scheme"],
  [/select option,\s*select optgroup\s*\{[^}]*color:\s*#d9e2ea\s*;[^}]*background-color:\s*#0f1a21\s*;/, "option popup foreground and background"],
  [/select option:disabled\s*\{[^}]*color:\s*#647b85\s*;/, "disabled option contrast"],
];

for (const [pattern, description] of requiredRules) {
  if (!pattern.test(styles)) {
    throw new Error(`Missing ${description} rule in styles.css`);
  }
}

console.log("Native select popup contrast contract passed.");
