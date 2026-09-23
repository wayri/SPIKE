/** Explain a failed operation without mistaking a mesh advisory for its cause. */
export function analysisFailure(issues: unknown, fallback: string): string {
  if (!Array.isArray(issues)) return fallback;
  const errors = issues.filter(item => item && item.severity === "error" && typeof item.message === "string" && item.message.trim());
  if (!errors.length) return fallback;
  return errors.map(item => `${item.code ? `[${item.code}] ` : ""}${item.message}${item.suggestion ? ` ${item.suggestion}` : ""}`).join("\n");
}
