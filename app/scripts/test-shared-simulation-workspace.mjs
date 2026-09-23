import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { simulationDomainLabel, workspaceForSimulationAction } from "../src/sharedSimulationWorkspace.ts";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const app = fs.readFileSync(path.join(root, "src", "App.tsx"), "utf8");
const shortcuts = fs.readFileSync(path.join(root, "src", "shortcutCatalog.ts"), "utf8");
const styles = fs.readFileSync(path.join(root, "src", "styles.css"), "utf8");

assert.equal(workspaceForSimulationAction("configure-mesh"), "Mesh");
assert.equal(workspaceForSimulationAction("extract"), "Mesh");
assert.equal(workspaceForSimulationAction("run"), "Solve");
assert.equal(simulationDomainLabel("si"), "Signal integrity");
assert.match(app, /name: "Mesh"/);
assert.match(app, /name: "Solve"/);
assert.match(app, /<SimulationWorkspace/);
assert.match(app, /data-shared-stage=\{sharedStage\.toLowerCase\(\)\}/, "the mounted PI setup must expose its shared stage to rendering");
assert.match(app, /aria-label="Shared simulation stage"/, "the PI setup must provide accessible Mesh and Solve tabs");
assert.match(styles, /data-shared-stage="mesh"[^}]*\.solve-only/s, "Mesh must hide solve-only terminal controls");
assert.match(styles, /data-shared-stage="solve"[^}]*option\[value="surface_2_5d"\]/s, "Solve must hide mesh discretization controls");
assert.match(styles, /data-shared-stage="mesh"[^}]*\.pi-dialog-actions \.run-btn/s, "Mesh must not expose the solver run action");
assert.match(app, /tab === "Mesh" && !selected[\s\S]{0,500}Solver selection and execution are available in the Solve tab/, "Mesh must replace the solver inspector with mesh-specific controls");
assert.match(app, /<div hidden=\{!sparameterOpen\}><SParameterWorkbench/, "SI setup must remain mounted while shared tabs are selected");
assert.doesNotMatch(app, /const terminal = activity\.phase[\s\S]{0,180}setAnalysisRunning\(false\)/, "unrelated worker terminal events must not clear global analysis state");
assert.match(app, /activity\.heavy[\s\S]{0,500}current\?\.id === activity\.operationId \? null : current/, "heavy worker completion must clear only its matching operation ID");
assert.match(app, /const universalRunning = analysisRunning \|\| Boolean\(activeWorkerOperation\)/, "universal Stop must include local and tracked heavy work");
assert.match(app, /cancelLocalWorker\(activeWorkerOperation\?\.id\)/, "universal Stop must target the tracked operation when present");
assert.match(shortcuts, /openMeshWorkspace/);
assert.match(shortcuts, /openSolveWorkspace/);

console.log("shared simulation workspace: all assertions passed");
