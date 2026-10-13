// SPDX-License-Identifier: Apache-2.0
// Visual acceptance of actual worker results from original synthetic fixtures.
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import SmpsConverterPanel, { type SmpsConverterRequest } from "../src/SmpsConverterPanel";
import CapacitorPlacementPanel, { CapacitorPlacementResults, type CapacitorPlacementResult } from "../src/CapacitorPlacementPanel";
import PiReturnPathAssistant from "../src/PiReturnPathAssistant";
import fixture from "./fixtures/pi-engineering-result.json";
import "../src/buttonStandard.css";

function Preview() {
  const [tab, setTab] = useState("converter");
  const [selected, setSelected] = useState(fixture.capacitor.result.best_candidate_id ?? "");
  return <main style={{ maxWidth: 1250, margin: "auto", padding: 16 }}>
    <p>SPIKE PI tools verification: original synthetic fixtures; actual worker results.</p>
    <nav style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      {["converter", "capacitors", "return"].map(name => <button className="spike-control--compact" aria-pressed={tab === name} key={name} onClick={() => setTab(name)}>{name}</button>)}
    </nav>
    {tab === "converter" && <SmpsConverterPanel workerAvailable components={[]}
      initialRequest={fixture.smps.request as SmpsConverterRequest} initialResult={fixture.smps.result} />}
    {tab === "capacitors" && <><CapacitorPlacementResults result={fixture.capacitor.result as CapacitorPlacementResult}
      selectedId={selected} onSelect={setSelected} /><CapacitorPlacementPanel workerAvailable /></>}
    {tab === "return" && <PiReturnPathAssistant workerAvailable design={fixture.return.design} occurrenceId="board-1" forwardNet="VCC" />}
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
