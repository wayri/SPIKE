// SPDX-License-Identifier: Apache-2.0
import { Children, Fragment, cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";

type NodeProps = { children?: ReactNode; value?: unknown; defaultValue?: unknown; type?: string; checked?: boolean; "data-search-text"?: string };
export type TableRowGroup = { key: string; body: number; node: ReactElement<NodeProps> };

/** Search displayed values, never all the unselected choices in a select. */
export function tableSearchText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!isValidElement<NodeProps>(node)) return Array.isArray(node) ? node.map(tableSearchText).join(" ") : "";
  const props = node.props;
  if (props["data-search-text"] !== undefined) return props["data-search-text"];
  // Quoted phrases cannot accidentally straddle adjacent cells.
  if (node.type === "td" || node.type === "th") return `\n${tableSearchText(props.children)}\n`;
  if (node.type === "select") {
    const value = props.value ?? props.defaultValue;
    const selected: string[] = [];
    const visit = (children: ReactNode) => Children.forEach(children, child => {
      if (!isValidElement<NodeProps>(child)) return;
      if (child.type === "option" && String(child.props.value ?? tableSearchText(child.props.children)) === String(value)) selected.push(tableSearchText(child.props.children));
      else if (child.type === "optgroup" || child.type === Fragment) visit(child.props.children);
    });
    visit(props.children);
    return `${String(value ?? "")} ${selected.join(" ")}`;
  }
  if (node.type === "input" && (props.type === "checkbox" || props.type === "radio")) return props.checked ? "enabled" : "disabled";
  if (props.value !== undefined || props.defaultValue !== undefined) return String(props.value ?? props.defaultValue ?? "");
  return tableSearchText(props.children);
}

/** A keyed fragment keeps an editable record and its expanded detail row together. */
export function tableRowGroups(children: ReactNode): TableRowGroup[] {
  const result: TableRowGroup[] = [];
  Children.toArray(children).forEach((section, body) => {
    if (!isValidElement<NodeProps>(section) || section.type !== "tbody") return;
    Children.toArray(section.props.children).forEach(node => {
      if (isValidElement<NodeProps>(node)) result.push({ key: `${body}:${node.key}`, body, node });
    });
  });
  return result;
}

export function matchTableRows(groups: readonly TableRowGroup[], query: string, activeKey: string | null = null) {
  const terms = Array.from(query.trim().toLocaleLowerCase().matchAll(/"([^"]+)"|(\S+)/g), match => match[1] ?? match[2]);
  if (!terms.length) return groups;
  return groups.filter(group => {
    if (group.key === activeKey) return true; // Keep the input mounted during an edit.
    const text = tableSearchText(group.node).toLocaleLowerCase();
    return terms.every(term => text.includes(term));
  });
}

export function tablePage<T>(rows: readonly T[], requestedPage: number, pageSize: number) {
  const size = Number.isFinite(pageSize) ? Math.max(1, Math.floor(pageSize)) : 100;
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const page = Math.max(0, Math.min(pages - 1, requestedPage));
  return { page, pages, start: page * size, rows: rows.slice(page * size, (page + 1) * size) };
}

function identifyRow(node: ReactElement<NodeProps>, key: string): ReactNode {
  if (node.type === "tr") return cloneElement(node as ReactElement<Record<string, unknown>>, { "data-table-row": key });
  if (node.type === Fragment) return cloneElement(node, {}, Children.map(node.props.children, child =>
    isValidElement<NodeProps>(child) ? identifyRow(child, key) : child));
  return node;
}

export function renderTableBodies(children: ReactNode, groups: readonly TableRowGroup[]): ReactNode {
  const byBody = new Map<number, ReactNode[]>();
  for (const group of groups) {
    if (!byBody.has(group.body)) byBody.set(group.body, []);
    byBody.get(group.body)!.push(identifyRow(group.node, group.key));
  }
  return Children.toArray(children).map((section, body) => {
    if (!isValidElement<NodeProps>(section) || section.type !== "tbody") return section;
    return cloneElement(section, {}, byBody.get(body) ?? []);
  });
}
