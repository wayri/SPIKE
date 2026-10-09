// SPDX-License-Identifier: Apache-2.0
import type { LucideIcon } from "./icons";
import "./AssemblyIconToolbar.css";

export type AssemblyToolbarAction = {
  id: string;
  label: string;
  text: string;
  icon: LucideIcon;
  onClick: () => void;
  pressed?: boolean;
  disabled?: boolean;
};

/** Mini labels preserve discoverability; full descriptions remain available to
 * keyboard users and assistive technology as well as pointer tooltips. */
export default function AssemblyIconToolbar({ actions, label = "Assembly view tools" }: {
  actions: AssemblyToolbarAction[];
  label?: string;
}) {
  return <div className="assembly-icon-toolbar" role="toolbar" aria-label={label}>
    {actions.map(({ id, label: description, text, icon: Icon, onClick, pressed, disabled }) =>
      <button key={id} type="button" className={`spike-control--compact assembly-icon-tool${pressed ? " selected" : ""}`}
        aria-label={description} title={description} aria-pressed={pressed} disabled={disabled} onClick={onClick}>
        <Icon size={17} aria-hidden="true"/><span>{text}</span>
      </button>)}
  </div>;
}
