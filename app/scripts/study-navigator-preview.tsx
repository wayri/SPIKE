// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import StudyNavigator from "../src/StudyNavigator";
import type { SimulationStudy, StudyRun } from "../src/simulationStudies";
import "../src/buttonStandard.css";
const runs: StudyRun[] = [
  { id: "captured-1", capturedAt: "2026-10-08T15:10:00Z", association: "workspace-capture", caseType: "thermal", mode: "layered steady", scenario: {}, settings: {}, facts: { status: "completed", modelStatus: "approximate" }, resultSnapshot: { temperature_c: 61 } },
  { id: "captured-2", capturedAt: "2026-10-09T11:30:00Z", association: "workspace-capture", caseType: "thermal", mode: "layered transient", scenario: {}, settings: {}, facts: { modelStatus: "approximate" }, resultRef: "results/chassis-temperature-history.json" },
];
const studies: SimulationStudy[] = [{ version: 1, id: "enclosure", name: "Thermal enclosure - high ambient with full board dissipation", notes: "", tags: [], archived: false, datasets: [], cases: [
  { id: "warm", type: "thermal", mode: "layered transient", name: "Sealed enclosure at 45 C ambient with extended source component and harness names", notes: "", scenario: {}, settings: {}, runs, datasetIds: [], resultSnapshot: { temperature_c: 61 } },
  { id: "baseline", type: "pi", mode: "dc", name: "Baseline current path", notes: "", scenario: {}, settings: {}, runs: [], datasetIds: [] },
] }, { version: 1, id: "archived", name: "Archived ambient investigation", notes: "", tags: [], archived: true, datasets: [], cases: [] }];
function Preview() {
  const [docked, setDocked] = useState(true);
  const [activeCaseId, setActiveCaseId] = useState<string | null>("warm");
  const [message, setMessage] = useState("Static interaction fixture. Result payloads are illustrative, not solver evidence.");
  return <main style={{ display: "flex", minHeight: "90vh", gap: 20, padding: 16, background: "var(--spike-table-surface)", color: "var(--spike-table-text)", fontFamily: "system-ui" }}>
    <div style={{ width: 330, height: 630, flex: "none" }}><StudyNavigator studies={studies} activeCaseId={activeCaseId} docked={docked} onFloat={() => setDocked(false)} onDock={() => setDocked(true)} onClose={() => setMessage("Close requested")}
      onManage={() => setMessage("Study Manager requested")} onActivateCase={(_, item) => { setActiveCaseId(item.id); setMessage(`Activated saved setup and result: ${item.name}`); }} onOpenRun={(_, item, run) => setMessage(run.resultSnapshot === undefined ? `Locate payload required for ${item.name}: ${run.resultRef}` : `Opened captured payload from ${run.capturedAt}`)}
      projectResults={[{ id: "board", name: "Board temperature history outside studies with an extended result name", detail: "Approximate / project capture", onOpen: () => setMessage("Opened project board temperature history") }, { id: "network", name: "Saved S-parameter sweep", detail: "Unvalidated / project result", onOpen: () => setMessage("Opened project network result") }]} /></div>
    <section style={{ minWidth: 0 }}><h2>Study navigator interaction fixture</h2><p role="status" style={{ overflowWrap: "anywhere" }}>{message}</p><p>Exercise at 1440 px and 800 px widths. Use arrow keys, Enter, double click, search, archived visibility, and Float/Dock. This preview verifies presentation and callbacks only.</p></section>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
