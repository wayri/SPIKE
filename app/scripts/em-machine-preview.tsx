// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { EmMachineWorkbench, type EmMachineStudy } from "../src/EmMachineWorkbench";
import motor from "../.tmp/em-machines/motor.json";
import generator from "../.tmp/em-machines/generator.json";
import magnet from "../.tmp/em-machines/electromagnet.json";
import "../src/styles.css";
import "../src/buttonStandard.css";
function Preview() {
  const examples = { motor, generator, electromagnet: magnet };
  const [study, setStudy] = useState<EmMachineStudy>(motor as EmMachineStudy);
  return <main style={{ maxWidth: 920, margin: "auto", padding: 16, height: "100vh", overflow: "auto", boxSizing: "border-box" }}>
    <h1>Executed machine result verification</h1>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{Object.entries(examples).map(([name, value]) =>
      <button key={name} onClick={() => setStudy(value as EmMachineStudy)}>Load {name} example</button>)}</div>
    <EmMachineWorkbench study={study} onStudy={setStudy} busy={false} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
