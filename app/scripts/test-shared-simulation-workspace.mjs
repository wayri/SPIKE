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
assert.match(app, /label="Ports"[^>]*onClick=\{\(\) => siSParameterSolver === "emerge" && emergeSiAvailable \? openSiEmerge\(\) : openSiWorkbench\("workflow", "ports"\)\}/, "SI ports must open EMerge setup when selected or source and receiver assignments otherwise");
assert.match(app, /label="NEXT \/ FEXT" onClick=\{\(\) => openSiWorkbench\("geometry", "crosstalk"\)\}/, "NEXT/FEXT must open a runnable coupled channel setup");
assert.match(app, /siWorkspace\s*\? <div className="results-strip"/, "SI workspace must show SI status rather than stale PI metrics");
assert.doesNotMatch(app, /const terminal = activity\.phase[\s\S]{0,180}setAnalysisRunning\(false\)/, "unrelated worker terminal events must not clear global analysis state");
assert.match(app, /activity\.heavy[\s\S]{0,500}current\?\.id === activity\.operationId \? null : current/, "heavy worker completion must clear only its matching operation ID");
assert.match(app, /const universalRunning = analysisRunning \|\| Boolean\(activeWorkerOperation\)/, "universal Stop must include local and tracked heavy work");
assert.match(app, /cancelLocalWorker\(activeWorkerOperation\?\.id\)/, "universal Stop must target the tracked operation when present");
assert.match(shortcuts, /openMeshWorkspace/);
assert.match(shortcuts, /openSolveWorkspace/);

console.log("shared simulation workspace: all assertions passed");

const [{build}, {default:React}, {renderToStaticMarkup}, {pathToFileURL}] = await Promise.all([
  import("esbuild"), import("react"), import("react-dom/server"), import("node:url"),
]);
const output=path.join(root,"scripts",`.simulation-workspace-test-${process.pid}.mjs`);
try {
  await build({entryPoints:[path.join(root,"src","SimulationWorkspace.tsx")],outfile:output,bundle:true,platform:"node",format:"esm",external:["react","react-dom","lucide-react"],logLevel:"silent"});
  const {default:Workspace}=await import(pathToFileURL(output).href);
  for(const tab of ["Mesh","Solve"]) for(const domain of ["pi","si"]) {
    const calls=[];
    const props={tab,domain,analysisMode:"Configured analysis",net:"Long explicit net name for the current domain",meshSummary:"0.5 mm target",solverName:"Configured solver",running:false,hasBoard:true,canExtract:true,
      onDomain(){},onConfigure(){},onNets(){},onStackup(){},onExtract:()=>calls.push("extract"),onRun:()=>calls.push("run"),onStop:()=>calls.push("stop"),onHarness(){},onTetraMesh(){}};
    const classic=renderToStaticMarkup(React.createElement(Workspace,props));
    assert.ok(!classic.includes("<details"),"Classic remains expanded by default");
    assert.ok(classic.includes("simulation-workspace-grid"));
    const compact=Workspace({...props,compact:true});
    const [details,action]=compact.props.children;
    assert.equal(details.type,"details","setup uses native keyboard-accessible disclosure");
    assert.ok(!details.props.open,"Clean starts with secondary setup collapsed");
    assert.equal(action.props.disabled,false);
    action.props.onClick();
    assert.equal(calls.pop(),tab==="Mesh"?"extract":"run","the compact primary action preserves the stage callback");
    const summary=renderToStaticMarkup(details.props.children[0]);
    assert.ok(summary.includes(tab)&&summary.includes(domain.toUpperCase())&&summary.includes(props.net),"the one-line summary retains stage, domain and exact net context");
    const retained=renderToStaticMarkup(details.props.children[1]);
    assert.ok(retained.includes("simulation-workspace-grid")&&retained.includes(tab==="Mesh"?"Explicit tetra mesh":"Harness PI"),"secondary controls remain mounted under the disclosure");
    const unavailable=Workspace({...props,compact:true,hasBoard:false}).props.children[1];
    assert.equal(unavailable.props.disabled,true,"missing designs cannot start work");
    if(tab==="Mesh")assert.equal(Workspace({...props,compact:true,canExtract:false}).props.children[1].props.disabled,true,"extraction retains its explicit-net eligibility gate");
    const stop=Workspace({...props,compact:true,running:true,hasBoard:false}).props.children[1];
    assert.equal(stop.props.disabled,false,"Stop remains reachable during an active operation");
    stop.props.onClick();assert.equal(calls.pop(),"stop","Stop keeps its cancellation callback");
  }
  console.log("Compact simulation disclosure: Classic default, retained setup, stage action callbacks, extraction admission and reachable Stop passed.");
} finally {
  for(const filename of [output,output.replace(/\.mjs$/,".css")])try{fs.unlinkSync(filename);}catch{}
}
