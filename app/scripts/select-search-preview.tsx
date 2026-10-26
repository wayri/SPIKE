// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import SelectSearchLayer from "../src/SelectSearchLayer";
import SolverSetupSteps, { SolverSetupPanel } from "../src/SolverSetupSteps";
import "../src/buttonStandard.css";

function Fixture() {
  const [net, setNet] = useState("GND"), [step, setStep] = useState("domain"), [voltage, setVoltage] = useState("3.3");
  return <main style={{ padding: 20, maxWidth: 920, margin: "auto", color: "var(--spike-table-text)", font: "13px/1.5 system-ui" }}>
    <SelectSearchLayer/>
    <h1 style={{ fontSize: 20 }}>Focused solver setup</h1><p>Actual shared controls · illustrative form only · no solver execution</p>
    <SolverSetupSteps label="Setup navigation" current={step} onChange={setStep} steps={[
      { id: "domain", label: "Geometry & domain", description: "Select the board and analysis net. Search choices by name or wildcard." },
      { id: "loads", label: "Sources & loads", description: "Enter supply voltage and loading. Existing validation still applies." },
      { id: "mesh", label: "Mesh & solver", description: "Choose a supported method and inspect mesh controls." },
      { id: "review", label: "Review & run", description: "Review all inputs before invoking the existing run action." },
    ]}/>
    <SolverSetupPanel active={step === "domain"} label="Geometry and domain fields"><label style={{ display: "grid", gap: 6, maxWidth: 460 }}>Analysis net<select id="nets" value={net} onChange={event => setNet(event.target.value)}>
      <option value="GND">GND · Main ground plane</option><optgroup label="Power rails"><option value="VCC_3V3">VCC_3V3 · Processor supply</option><option value="VCC_5V">VCC_5V · Input supply</option><option disabled value="VCC_12V">VCC_12V · Missing terminals</option></optgroup>
      <optgroup label="Signal nets">{Array.from({ length: 250 }, (_, i) => <option key={i} value={`CLK_${i}`}>CLK_{i} · Long connector and occurrence name for selection clarity</option>)}</optgroup>
    </select></label><p>Selected: <output id="selection">{net}</output></p></SolverSetupPanel>
    <SolverSetupPanel active={step === "loads"} label="Source fields"><label>Supply voltage (V)<input id="supply" value={voltage} onChange={event => setVoltage(event.target.value)}/></label><label>Unfinished draft<input id="local-draft" defaultValue="1e-"/></label></SolverSetupPanel>
    <SolverSetupPanel active={step === "mesh"} label="Mesh fields"><label>Method<select><option>Admitted built-in workflow</option><option disabled>Unavailable extension</option></select></label></SolverSetupPanel>
    <SolverSetupPanel active={step === "review"} label="Review fields"><p>{net} · {voltage} V</p><button disabled>Run (fixture only)</button></SolverSetupPanel>
    <fieldset disabled><label>Locked field<select id="locked"><option>Do not change</option></select></label></fieldset>
    <dialog id="native-dialog" style={{ background: "var(--spike-table-surface)", color: "var(--spike-table-text)", border: "1px solid var(--spike-table-border)", padding: 20 }}><label>Dialog scale<select id="dialog-select"><option>Linear</option><option>Logarithmic</option></select></label></dialog>
    <div style={{ marginTop: 20 }}><button id="outside">Outside control</button></div><output id="acceptance" style={{ display: "block", marginTop: 20 }}/>
  </main>;
}
document.body.style.background = "var(--spike-table-surface)";
createRoot(document.getElementById("root")!).render(<Fixture/>);
if (new URLSearchParams(location.search).has("qualify")) void (async () => {
  const tick = () => new Promise(resolve => setTimeout(resolve, 80)); await tick();
  const get = <T extends HTMLElement>(selector: string) => { const element = document.querySelector<T>(selector); if (!element) throw new Error(`Missing ${selector}`); return element; };
  const check = (value: unknown, message: string) => { if (!value) throw new Error(message); };
  const open = async () => { get("#nets").dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 })); await tick(); };
  const search = async (value: string) => { const input = get<HTMLInputElement>('.select-search input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); await tick(); };
  try {
    get("#locked").dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 })); await tick();
    check(!document.querySelector(".select-search"), "disabled fieldset cannot open editable choices");
    await open(); check(!!document.querySelector(".select-search"), "native select opens integrated search");
    await search("input VCC_?V"); check(document.querySelectorAll('[role="option"]').length === 1, "? wildcard");
    check(get("#selection").textContent === "GND", "search cannot change selected value");
    get<HTMLButtonElement>('[role="option"]').click(); await tick(); check(get("#selection").textContent === "VCC_5V", "native React handler receives selection");
    await open(); await search("VCC_12*"); check(get<HTMLButtonElement>('[role="option"]').disabled, "disabled option remains unavailable");
    get<HTMLInputElement>('.select-search input').dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await tick();
    check(!document.querySelector(".select-search") && document.activeElement === get("#nets"), "Escape restores focus");
    await open(); await search("no-such-net"); check(document.querySelector('.select-search [role="status"]')?.textContent?.includes("No matching"), "empty search recovery");
    get("#outside").dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })); await tick(); check(!document.querySelector(".select-search"), "outside dismisses");
    get<HTMLButtonElement>('.solver-step-navigation button:last-child').click(); await tick();
    check(!get("#supply").closest("[hidden]"), "Next opens source step");
    get<HTMLInputElement>("#local-draft").value = "unfinished 1e-";
    get<HTMLButtonElement>('.solver-step-navigation button:first-child').click(); await tick(); check(get<HTMLInputElement>("#supply").value === "3.3" && get<HTMLInputElement>("#local-draft").value === "unfinished 1e-", "step navigation retains controlled and local unfinished drafts");
    get<HTMLDialogElement>("#native-dialog").showModal(); await tick();
    get("#dialog-select").dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 })); await tick();
    check(get<HTMLDialogElement>("#native-dialog").contains(get(".select-search")) && document.activeElement === get('.select-search input'), "native modal dropdown remains in its top layer and accepts focus");
    await search("log*"); get<HTMLButtonElement>('[role="option"]').click(); await tick();
    check(get<HTMLSelectElement>("#dialog-select").value === "Logarithmic", "native dialog selection commits");
    get<HTMLDialogElement>("#native-dialog").close(); await tick();
    await open(); await search("CLK_2*");
    const rect = get(".select-search").getBoundingClientRect(); check(rect.width >= 200 && rect.height >= 80 && rect.left >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight, `popover bounds ${JSON.stringify(rect.toJSON())}`);
    await new Promise(resolve => setTimeout(resolve, 350)); check(!!document.querySelector(".select-search"), "popover stays open after layout settles");
    const popupStyle = getComputedStyle(get(".select-search"));
    get("#acceptance").dataset.debug = JSON.stringify({opacity:popupStyle.opacity,visibility:popupStyle.visibility,display:popupStyle.display,z:popupStyle.zIndex,hit:document.elementFromPoint(rect.left+10,rect.top+10)?.outerHTML.slice(0,100)});
    get("#acceptance").textContent = "PASS: wildcard filtering, controlled select dispatch, native modal focus, disabled/empty/outside/Escape recovery, retained setup steps and popup bounds";
  } catch (error) { get("#acceptance").textContent = `FAIL: ${String(error)}`; }
})();
