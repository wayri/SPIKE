import { Boxes, Cable, Cpu, Grid3X3, Layers3, Play, ShieldAlert, SlidersHorizontal, SquareTerminal, Waves } from "lucide-react";
import type { SimulationDomain, SimulationWorkspaceTab } from "./sharedSimulationWorkspace";
import { simulationDomainLabel } from "./sharedSimulationWorkspace";

type Props = {
  tab: SimulationWorkspaceTab; domain: SimulationDomain; analysisMode: string; net: string;
  meshSummary: string; solverName: string; running: boolean; hasBoard: boolean; canExtract: boolean;
  onDomain: (domain: SimulationDomain) => void; onConfigure: () => void; onNets: () => void;
  onStackup: () => void; onExtract: () => void; onRun: () => void; onStop: () => void;
  onHarness?: () => void;
  onTetraMesh?: () => void;
};

export default function SimulationWorkspace(props: Props) {
  const mesh = props.tab === "Mesh";
  return <section className="simulation-workspace" aria-label={`${props.tab} workspace`}>
    <header>
      <div><span>SHARED SIMULATION WORKSPACE</span><h2>{props.tab}</h2><p>{mesh
        ? "Review the geometry and discretization inputs used by PI and SI workflows."
        : "Run the configured PI analysis or continue to SI extraction from one execution surface."}</p></div>
      <div className="simulation-domain-switch" aria-label="Simulation domain">
        {(["pi", "si"] as const).map(domain => <button key={domain} className={props.domain === domain ? "selected" : ""} onClick={() => props.onDomain(domain)}>{simulationDomainLabel(domain)}</button>)}
      </div>
    </header>
    <div className="simulation-workspace-grid">
      <article><span>ACTIVE DOMAIN</span><b>{simulationDomainLabel(props.domain)}</b><small>{props.analysisMode}</small></article>
      <article><span>ANALYSIS NET</span><b>{props.net || "Not selected"}</b><small>Use Nets to choose the explicit domain.</small></article>
      <article><span>{mesh ? "MESH SETUP" : "SOLVER"}</span><b>{mesh ? props.meshSummary : props.solverName}</b><small>{mesh ? `Saved with the current ${props.domain.toUpperCase()} setup.` : "Availability remains capability-gated."}</small></article>
    </div>
    {!props.hasBoard && <div className="simulation-workspace-notice"><ShieldAlert size={16} /> Import a design before configuring mesh or solver execution.</div>}
    <div className="simulation-workspace-actions">
      {mesh ? <>
        <button onClick={props.onConfigure} disabled={!props.hasBoard}><SlidersHorizontal size={16} /> Mesh settings</button>
        <button onClick={props.onNets} disabled={!props.hasBoard}><SquareTerminal size={16} /> Nets and terminals</button>
        <button onClick={props.onStackup} disabled={!props.hasBoard}><Layers3 size={16} /> Stackup</button>
        {props.onTetraMesh && <button onClick={props.onTetraMesh}><Boxes size={16} /> Explicit tetra mesh</button>}
        <button className="primary" onClick={props.onExtract} disabled={!props.hasBoard || !props.canExtract}><Cpu size={16} /> Extract RLC</button>
      </> : <>
        <button onClick={props.onConfigure} disabled={!props.hasBoard}><SlidersHorizontal size={16} /> Review setup</button>
        <button onClick={props.onNets} disabled={!props.hasBoard}><Grid3X3 size={16} /> Analysis domain</button>
        {props.onHarness && <button onClick={props.onHarness}><Cable size={16} /> Harness PI</button>}
        {props.domain === "si" && <button onClick={props.onExtract} disabled={!props.hasBoard || !props.canExtract}><Waves size={16} /> SI extraction</button>}
        <button className={props.running ? "danger" : "primary"} onClick={props.running ? props.onStop : props.onRun} disabled={!props.hasBoard}><Play size={16} /> {props.running ? "Stop" : props.domain === "pi" ? "Open run controls" : "Open extraction controls"}</button>
      </>}
    </div>
  </section>;
}
