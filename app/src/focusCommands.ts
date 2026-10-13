// SPDX-License-Identifier: Apache-2.0
import { Children, Fragment, isValidElement, type ElementType, type ReactElement, type ReactNode } from "react";

export type FocusCommand = {
  id: string;
  label: string;
  icon?: ElementType;
  shortcut?: string;
  disabled?: boolean;
  checked?: boolean;
  radio?: boolean;
  run?: () => void | Promise<void>;
  children?: readonly FocusCommand[];
  content?: ReactNode;
  onEnter?: () => void | Promise<void>;
};

export type FocusCommandMatch = { command: FocusCommand; path: readonly string[]; ancestors: readonly FocusCommand[] };

type ElementProps = {
  "aria-label"?: unknown;
  children?: ReactNode;
  className?: unknown;
  disabled?: unknown;
  icon?: unknown;
  label?: unknown;
  onClick?: unknown;
  onEnter?: unknown;
  shortcut?: unknown;
  title?: unknown;
  actions?: unknown;
};

type ActionProps = { label?: unknown; icon?: unknown; shortcut?: unknown; disabled?: unknown; checked?: unknown; radio?: unknown; run?: unknown };

const slug = (value: string) => value.trim().toLocaleLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "command";

function textBeforeControl(node: ReactNode): string {
  const parts: string[] = [];
  const visit = (value: ReactNode) => {
    if (typeof value === "string" || typeof value === "number") { parts.push(String(value)); return; }
    if (!isValidElement<ElementProps>(value)) return;
    if (typeof value.type === "string" && ["button", "input", "select", "textarea"].includes(value.type)) return;
    Children.forEach(value.props.children, visit);
  };
  Children.forEach(node, visit);
  return parts.join(" ").replace(/\s+/g, " ").trim();
}

function containsControl(node: ReactNode): boolean {
  let found = false;
  Children.forEach(node, value => {
    if (found || !isValidElement<ElementProps>(value)) return;
    if (typeof value.type === "string" && ["button", "input", "select", "textarea"].includes(value.type)) found = true;
    else found = containsControl(value.props.children);
  });
  return found;
}

function safeContent(element: ReactElement<ElementProps>): FocusCommand | null {
  if (typeof element.type !== "string") return null;
  const control = ["input", "select", "textarea"].includes(element.type);
  const container = ["label", "div", "span"].includes(element.type) && containsControl(element.props.children);
  if (!control && !container) return null;
  const label = typeof element.props["aria-label"] === "string" ? element.props["aria-label"]
    : typeof element.props.title === "string" ? element.props.title
      : typeof element.props.label === "string" ? element.props.label : textBeforeControl(element.props.children);
  return label ? { id: "", label, disabled: element.props.disabled === true, content: element } : null;
}

function nativeAction(element: ReactElement<ElementProps>): Omit<FocusCommand, "id"> | null {
  if (element.type !== "button" || typeof element.props.onClick !== "function") return null;
  const label = typeof element.props["aria-label"] === "string" ? element.props["aria-label"]
    : typeof element.props.title === "string" ? element.props.title : textBeforeControl(element.props.children);
  return label ? { label, disabled: element.props.disabled === true, run: element.props.onClick as FocusCommand["run"] } : null;
}

/**
 * Reads command metadata from already-created React elements. Component
 * functions are never rendered or called; only their public props are read.
 */
export function focusCommandsFromElements(nodes: ReactNode, prefix = "focus"): FocusCommand[] {
  const root = slug(prefix);
  const extract = (input: ReactNode, parentId: string): FocusCommand[] => {
    const result: FocusCommand[] = [], duplicates = new Map<string, number>();
    const identity = (label: string) => {
      const base = slug(label), count = (duplicates.get(base) ?? 0) + 1;
      duplicates.set(base, count);
      return `${parentId}-${base}${count === 1 ? "" : `-${count}`}`;
    };
    for (const node of Children.toArray(input)) {
      if (!isValidElement<ElementProps>(node)) continue;
      const props = node.props;
      if (node.type === Fragment) { result.push(...extract(props.children, parentId)); continue; }
      const content = safeContent(node);
      if (content) { result.push({ ...content, id: identity(content.label) }); continue; }
      const native = nativeAction(node);
      if (native) { result.push({ ...native, id: identity(native.label) }); continue; }
      const label = typeof props.label === "string" ? props.label.trim() : "";
      if (label && Array.isArray(props.actions)) {
        const id = identity(label), actionCounts = new Map<string, number>();
        const children = props.actions.flatMap((value: ActionProps) => {
          const actionLabel = typeof value?.label === "string" ? value.label.trim() : "";
          if (!actionLabel || typeof value.run !== "function") return [];
          const base = slug(actionLabel), count = (actionCounts.get(base) ?? 0) + 1;
          actionCounts.set(base, count);
          return [{ id: `${id}-${base}${count === 1 ? "" : `-${count}`}`, label: actionLabel,
            icon: value.icon as FocusCommand["icon"], shortcut: typeof value.shortcut === "string" ? value.shortcut : undefined,
            disabled: value.disabled === true, checked: typeof value.checked === "boolean" ? value.checked : undefined,
            radio: value.radio === true, run: value.run as FocusCommand["run"] } satisfies FocusCommand];
        });
        result.push({ id, label, icon: props.icon as FocusCommand["icon"], children });
      }
      else if (label && props.children !== undefined && props.children !== null) {
        const id = identity(label);
        result.push({
          id,
          label,
          icon: props.icon as FocusCommand["icon"],
          disabled: props.disabled === true,
          onEnter: typeof props.onEnter === "function" ? props.onEnter as FocusCommand["onEnter"] : undefined,
          children: extract(props.children, id),
        });
      } else if (label && typeof props.onClick === "function") {
        result.push({
          id: identity(label),
          label,
          icon: props.icon as FocusCommand["icon"],
          shortcut: typeof props.shortcut === "string" ? props.shortcut : undefined,
          disabled: props.disabled === true,
          run: props.onClick as FocusCommand["run"],
        });
      } else if (props.children !== undefined) result.push(...extract(props.children, parentId));
    }
    return result;
  };
  return extract(nodes, root);
}

/** Global leaf search retaining each result's complete menu path. */
export function searchFocusCommands(commands: readonly FocusCommand[], query: string): FocusCommandMatch[] {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean), result: FocusCommandMatch[] = [];
  const visit = (items: readonly FocusCommand[], path: readonly string[], ancestors: readonly FocusCommand[]) => {
    for (const command of items) {
      const next = [...path, command.label];
      if (command.children?.length) visit(command.children, next, [...ancestors, command]);
      else {
        const searchable = next.join(" ").toLocaleLowerCase();
        if (terms.every(term => searchable.includes(term))) result.push({ command, path: next, ancestors });
      }
    }
  };
  visit(commands, [], []);
  return result;
}
