// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { Focus, Layers3, Save, Settings2 } from "lucide-react";
import CommandStrip from "../../src/CommandStrip";
import "../../src/tableTheme.css";

function Fixture() {
  const [width, setWidth] = useState("420");
  const [theme, setTheme] = useState("professional-dark");
  const [selection, setSelection] = useState("none");
  const [count, setCount] = useState(0);
  const commands = ["Layers", "Fit board", "Focus selected", "Models", "Net isolation", "Stackup", "Analysis settings", "Save project"];
  return <main data-table-theme={theme} style={{ padding: 16, font: "12px system-ui", color: "var(--spike-table-text)", background: "var(--spike-table-surface)", minHeight: "100vh" }}>
    <h1>Command segments</h1>
    <p>Production command strip: resize, tab through commands, or use Home / End while the strip is focused.</p>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 20 }}>
      <label>Panel width <select value={width} onChange={e => setWidth(e.target.value)}><option>320</option><option>420</option><option>720</option><option>1100</option></select></label>
      <label>Theme <select value={theme} onChange={e => setTheme(e.target.value)}><option value="professional-dark">Dark</option><option value="light">Light</option><option value="high-contrast">High contrast</option><option value="system">System</option></select></label>
      <label>Selection <select value={selection} onChange={e => setSelection(e.target.value)}><option value="none">No selection</option><option value="board">Controller_board_with_a_very_long_occurrence_name_revision_12</option></select></label>
    </div>
    <section style={{ width: `min(${width}px, 100%)`, border: "1px solid var(--spike-table-border)", background: "var(--spike-table-toolbar)" }}>
      <header style={{ padding: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={selection === "none" ? "No selection" : "Controller_board_with_a_very_long_occurrence_name_revision_12"}>{selection === "none" ? "No selection" : "Controller_board_with_a_very_long_occurrence_name_revision_12"}</header>
      <CommandStrip label="Fixture viewport">
        {commands.map((command, index) => { const Icon = [Layers3, Focus, Settings2, Save][index % 4]; return <button key={command} type="button" title={command} disabled={command === "Focus selected" && selection === "none"} onClick={() => setCount(value => value + 1)} style={{ display: "flex", alignItems: "center", gap: 5, height: 28, padding: "0 8px", border: "1px solid var(--spike-table-border)", color: "var(--spike-table-text)", background: "var(--spike-table-surface)", font: "11px system-ui" }}><Icon size={15}/>{command}</button>; })}
      </CommandStrip>
      <p style={{ margin: 10 }}>Command invocations: {count}. Disabled Focus recovers when a board is selected.</p>
    </section>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
