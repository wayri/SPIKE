import type { ReactNode } from "react";

export type HelpTopic = { id: string; title: string; keywords: string; body?: ReactNode; markdown?: string; category?: string; source?: string };
export const helpSlug = (text: string) => text.toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s+/g, "-");
export function searchHelp<T extends { title: string; text: string }>(items: T[], query: string): T[] {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return items.map(item => {
    const title = item.title.toLowerCase(), text = item.text.toLowerCase();
    const score = terms.every(term => `${title} ${text}`.includes(term))
      ? terms.reduce((sum, term) => sum + (title.includes(term) ? 10 : 1), 0) : -1;
    return { item, score };
  }).filter(hit => hit.score >= 0).sort((a, b) => b.score - a.score).map(hit => hit.item);
}

export function resolveHelpLink(href: string, source: string): { id: string; anchor: string } | null {
  if (href.startsWith("help:")) { const [id, anchor = ""] = href.slice(5).split("#"); return { id, anchor }; }
  const [pathname, anchor = ""] = href.split("#");
  if (!pathname) return { id: `doc:${source}`, anchor };
  if (/^[a-z][a-z\d+.-]*:/i.test(pathname) || pathname.startsWith("//")) return null;
  const parts = [...source.split("/").slice(0, -1), ...pathname.split("/")];
  const normalized: string[] = [];
  for (const part of parts) { if (part === "..") normalized.pop(); else if (part !== "." && part) normalized.push(part); }
  return { id: `doc:${normalized.join("/")}`, anchor };
}
