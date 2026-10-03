// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import StudyManager from "../../src/StudyManager";
import { addStudyCase, createStudy, duplicateStudyCase, moveStudyCase, removeStudy, removeStudyCase, updateStudy, updateStudyCase, type SimulationStudy } from "../../src/simulationStudies";
import "../../src/styles.css";

const initial: SimulationStudy[] = [{
  version: 1, id: "rf-study", name: "RF front-end enclosure and antenna clearance review with a deliberately long study name",
  notes: "Compare retained openEMS snapshots without treating them as compliance evidence.", tags: ["rf", "enclosure", "prototype-b"], archived: false,
  datasets: [{ id: "measured-s11", name: "fixture-analyzer-export-with-long-source-name.csv", kind: "csv", mediaType: "text/csv", provenance: "Synthetic UI fixture; not measured hardware", units: { frequency: "Hz", s11: "dB" }, createdAt: "2026-09-28T10:00:00.000Z", resultDerived: false, rawText: "frequency_hz,s11_db\n1000000000,-8.2\n" }],
  cases: [{ id: "em-case", type: "em", mode: "openEMS port sweep", name: "Patch feed with enclosure wall and exceptionally long connector occurrence name", notes: "Fixture only", scenario: { label: "lid installed" }, settings: { mesh: "three-level", frequency_hz: [1e9, 2e9] }, datasetIds: ["measured-s11"], runs: [
    { id: "run-a", association: "workspace-capture", caseType: "em", mode: "openEMS port sweep", capturedAt: "2026-09-28T11:00:00.000Z", scenario: { label: "lid installed" }, settings: { mesh: "coarse" }, facts: { contract: "spike/openems-result/v1", status: "completed", modelStatus: "not_validated", designId: "board-a", designDigestSha256: "fixture-digest", units: { frequency: "Hz", s11: "dB" } }, resultSnapshot: { s11_db: [-8.2, -10.1], provenance: { fixture: true } } },
    { id: "run-b", association: "workspace-capture", caseType: "em", mode: "openEMS port sweep", capturedAt: "2026-09-29T11:00:00.000Z", scenario: { label: "lid installed" }, settings: { mesh: "medium" }, facts: { contract: "spike/openems-result/v1", status: "completed", modelStatus: "experimental", designId: "board-a", designDigestSha256: "fixture-digest", units: { frequency: "Hz", s11: "dB" } }, resultSnapshot: { s11_db: [-8.6, -10.4], provenance: { fixture: true } } },
  ] }],
}, { ...createStudy("Archived legacy thermal experiment"), id: "archived", archived: true, tags: ["legacy"] }];

function Fixture() {
  const [studies, setStudies] = useState(initial);
  const [active, setActive] = useState<string | null>("em-case");
  const [theme, setTheme] = useState<"dark" | "light" | "high-contrast">("dark");
  const updateOne = (id: string, fn: (study: SimulationStudy) => SimulationStudy) => setStudies(rows => rows.map(row => row.id === id ? fn(row) : row));
  const palette = theme === "light" ? { "--panel-bg": "#f4f7f9", "--panel-raised": "#ffffff", "--input-bg": "#ffffff", "--border-color": "#91a3ad", "--text-color": "#17252c", "--muted-text": "#526873", "--accent-color": "#087f91", "--danger-text": "#a62424", colorScheme: "light" } : theme === "high-contrast" ? { "--panel-bg": "#000000", "--panel-raised": "#050505", "--input-bg": "#000000", "--border-color": "#ffffff", "--text-color": "#ffffff", "--muted-text": "#e3e3e3", "--accent-color": "#00ffff", "--danger-text": "#ff8a8a", colorScheme: "dark" } : { colorScheme: "dark" };
  return <main data-theme={theme} style={{ ...palette, width: "100%", height: "100%" } as React.CSSProperties}><label style={{ position: "fixed", zIndex: 2200, right: 12, top: 2, color: "var(--text-color, #e7f1f5)", display: "flex", alignItems: "center", gap: 6 }}>Theme <select aria-label="Fixture theme" value={theme} onChange={event => setTheme(event.target.value as typeof theme)}><option value="dark">Dark</option><option value="light">Light</option><option value="high-contrast">High contrast</option></select></label><StudyManager studies={studies} currentType="em" activeCaseId={active}
    caseTypes={[{ value: "em", label: "Electromagnetics" }, { value: "si", label: "RF / signal integrity" }, { value: "pi", label: "Power integrity", disabled: true, description: "Unavailable in the EM product." }, { value: "thermal", label: "Thermal", disabled: true }]}
    onCreateStudy={() => { const study = createStudy(); setStudies(rows => [...rows, study]); return study.id; }}
    onUpdateStudy={(id, patch) => setStudies(rows => updateStudy(rows, id, patch))} onRemoveStudy={id => setStudies(rows => removeStudy(rows, id))}
    onAddCase={(id, type) => updateOne(id, study => addStudyCase(study, type))} onUpdateCase={(id, caseId, patch) => updateOne(id, study => updateStudyCase(study, caseId, patch))}
    onDuplicateCase={(id, caseId) => updateOne(id, study => duplicateStudyCase(study, caseId))} onRemoveCase={(id, caseId) => updateOne(id, study => removeStudyCase(study, caseId))}
    onMoveCase={(id, caseId, destination) => updateOne(id, study => moveStudyCase(study, caseId, destination))}
    onImportStudies={imported => setStudies(rows => [...rows, ...imported])}
    onActivateCase={(_, studyCase) => setActive(studyCase.id)} onSaveCaseSetup={() => {}} onCaptureCaseResult={() => {}} onOpenResult={() => {}} onClose={() => {}}/></main>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
