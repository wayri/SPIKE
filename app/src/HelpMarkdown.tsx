import { Fragment, useState } from "react";
import { helpSlug, resolveHelpLink } from "./helpModel";

export function CopyCode({ text }: { text: string }) {
  const [status, setStatus] = useState("");
  return <div className="help-code"><button onClick={() => void navigator.clipboard.writeText(text).then(() => setStatus("Copied"), () => setStatus("Select the text below to copy"))}>{status || "Copy"}</button><pre><code>{text}</code></pre><span className="help-sr" role="status">{status}</span></div>;
}

type Props = { text: string; source: string; navigate: (id: string, anchor?: string) => void; hasTopic: (id: string) => boolean };
// Restricted Markdown, rendered as React text. Raw HTML is never injected.
export default function HelpMarkdown({ text, source, navigate, hasTopic }: Props) {
  function inline(value: string): React.ReactNode[] {
    return value.split(/(!?\[[^\]]*\]\([^\s)]+\)|`[^`]+`|\*\*[^*]+\*\*)/g).map((part, index) => {
      const link = part.match(/^(!?)\[([^\]]*)\]\(([^\s)]+)\)$/);
      if (link) {
        const [, image, label, href] = link;
        if (image) {
          const filename = href.split("/").pop() ?? "";
          const allowed = ["marble-workspace-3d.png", "marble-layout-layers.png", "marble-net-names.png", "marble-report-preview.png", "marble-v1.4.4-top.png", "marble-v1.4.4-f-cu.svg", "workspace-3d.png", "layout-selection.png", "report-preview.png", "external-solver-center.png", "solver-extension-manager.png", "solver-manager-selection.png"];
          return allowed.includes(filename) ? <figure key={index}><a href={`/help/${filename}`} target="_blank" rel="noreferrer"><img loading="lazy" src={`/help/${filename}`} alt={label} /></a><figcaption>{label} · Select to enlarge</figcaption></figure> : <span key={index}>{label} (see source artifact: {href})</span>;
        }
        const target = resolveHelpLink(href, source);
        if (target && hasTopic(target.id)) return <a key={index} href={`#help/${encodeURIComponent(target.id)}${target.anchor ? `/${encodeURIComponent(target.anchor)}` : ""}`} onClick={event => { event.preventDefault(); navigate(target.id, target.anchor); }}>{label}</a>;
        if (/^https?:\/\//i.test(href)) return <a key={index} href={href} target="_blank" rel="noreferrer">{label}</a>;
        return <span key={index} title={href}>{label} <code>{href}</code></span>;
      }
      if (part.startsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
      if (part.startsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
      return <Fragment key={index}>{part}</Fragment>;
    });
  }
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: React.ReactNode[] = [];
  const headingCounts = new Map<string, number>();
  for (let i = 0; i < lines.length;) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (/^```/.test(line)) {
      const code: string[] = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
      i++; blocks.push(<CopyCode key={i} text={code.join("\n")} />); continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const base = helpSlug(heading[2]), count = headingCounts.get(base) ?? 0;
      headingCounts.set(base, count + 1);
      const id = count ? `${base}-${count}` : base;
      const Tag = `h${Math.min(heading[1].length + 1, 6)}` as "h2";
      blocks.push(<Tag id={id} key={i}>{inline(heading[2])}</Tag>); i++; continue;
    }
    if (line.trim().startsWith("|") && /^\s*\|?[\s:|-]+\|/.test(lines[i + 1] ?? "")) {
      const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map(cell => cell.trim().replace(/\\\|/g, "|"));
      const headers = cells(line); i += 2; const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      blocks.push(<div className="help-table-wrap" key={i}><table><thead><tr>{headers.map((cell, c) => <th key={c}>{inline(cell)}</th>)}</tr></thead><tbody>{rows.map((row, r) => <tr key={r}>{row.map((cell, c) => <td key={c}>{inline(cell)}</td>)}</tr>)}</tbody></table></div>); continue;
    }
    if (/^\s*(?:[-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line), rows: string[] = [];
      while (i < lines.length && /^\s*(?:[-*]|\d+\.)\s+/.test(lines[i])) {
        let item = lines[i++].replace(/^\s*(?:[-*]|\d+\.)\s+/, "");
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*(?:[-*]|\d+\.)\s+/.test(lines[i])) item += ` ${lines[i++].trim()}`;
        rows.push(item);
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(<Tag key={i}>{rows.map((item, r) => <li key={r}>{inline(item)}</li>)}</Tag>); continue;
    }
    if (/^>/.test(line)) { blocks.push(<blockquote key={i}>{inline(line.replace(/^>\s?/, ""))}</blockquote>); i++; continue; }
    if (/^---+$/.test(line)) { blocks.push(<hr key={i} />); i++; continue; }
    const paragraph = [line]; i++;
    while (i < lines.length && lines[i].trim() && !/^(#|```|\||>|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) paragraph.push(lines[i++]);
    blocks.push(<div className="help-paragraph" key={i}>{inline(paragraph.join(" "))}</div>);
  }
  return <>{blocks}</>;
}
