import { Gauge, Globe2, MonitorCog, Ruler, ShieldCheck, SlidersHorizontal, UserRound, X } from "lucide-react";
import { useEffect, useState } from "react";
import { AppSettings, LANGUAGE_NAMES } from "./appSettings";

type SettingsTab = "General" | "Units" | "Interface" | "Language" | "Profile" | "Privacy";

export default function UniversalSettingsModal({ settings, onSave, onClose }: { settings: AppSettings; onSave: (settings: AppSettings) => void; onClose: () => void }) {
  const [draft, setDraft] = useState<AppSettings>(() => structuredClone(settings));
  const [tab, setTab] = useState<SettingsTab>("General");
  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  const update = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => setDraft(current => ({ ...current, [key]: value }));
  const tabs: { id: SettingsTab; icon: typeof Gauge }[] = [
    { id: "General", icon: SlidersHorizontal }, { id: "Units", icon: Ruler }, { id: "Interface", icon: MonitorCog },
    { id: "Language", icon: Globe2 }, { id: "Profile", icon: UserRound }, { id: "Privacy", icon: ShieldCheck },
  ];
  return <div className="modal-shade settings-shade" role="dialog" aria-modal="true" aria-label="SPIKE settings">
    <section className="universal-settings">
      <header><div><b>Settings</b><span>Application, units, interface, language, profile, and privacy</span></div><button className="canvas-icon" onClick={onClose} aria-label="Close settings"><X size={16} /></button></header>
      <div className="settings-layout">
        <nav>{tabs.map(item => <button key={item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}><item.icon size={15} />{item.id}</button>)}</nav>
        <main>
          {tab === "General" && <SettingsSection title="Workspace">
            <Setting label="Restore last workspace"><input type="checkbox" checked={draft.restoreWorkspace} onChange={event => update("restoreWorkspace", event.target.checked)} /></Setting>
            <Setting label="Autosave interval"><select value={draft.autosaveMinutes} onChange={event => update("autosaveMinutes", Number(event.target.value) as AppSettings["autosaveMinutes"])}><option value={0}>Disabled</option><option value={1}>1 minute</option><option value={5}>5 minutes</option><option value={10}>10 minutes</option><option value={30}>30 minutes</option></select></Setting>
            <Setting label="Numerical precision"><input type="number" min={3} max={12} value={draft.significantDigits} onChange={event => update("significantDigits", Math.max(3, Math.min(12, Number(event.target.value))))} /></Setting>
            <Setting label="Solver memory fraction"><input type="number" min={10} max={90} step={5} value={Math.round(draft.solverMemoryFraction * 100)} onChange={event => update("solverMemoryFraction", Math.max(0.1, Math.min(0.9, Number(event.target.value) / 100)))} /><small>% of detected RAM</small></Setting>
            <Setting label="Solver memory limit"><input type="number" min={2} step={1} value={draft.solverMemoryLimitGb} onChange={event => update("solverMemoryLimitGb", Math.max(2, Number(event.target.value) || 2))} /><small>GB, minimum 2 GB</small></Setting>
            <p className="settings-note">The lower of the detected-RAM fraction and absolute GB limit is used for admission planning. Solver convergence, external-engine limits, and GPU capacity remain separate checks.</p>
          </SettingsSection>}
          {tab === "Units" && <SettingsSection title="Engineering units">
            <Setting label="Unit system"><select value={draft.unitSystem} onChange={event => update("unitSystem", event.target.value as AppSettings["unitSystem"])}><option value="engineering">Engineering SI</option><option value="si">Strict SI</option><option value="imperial">Imperial</option></select></Setting>
            <Setting label="Board coordinates"><select value={draft.coordinateUnit} onChange={event => update("coordinateUnit", event.target.value as AppSettings["coordinateUnit"])}><option value="mm">Millimetres</option><option value="mil">Mils</option><option value="inch">Inches</option></select></Setting>
            <Setting label="Temperature"><select value={draft.temperatureUnit} onChange={event => update("temperatureUnit", event.target.value as AppSettings["temperatureUnit"])}><option value="C">Celsius</option><option value="F">Fahrenheit</option><option value="K">Kelvin</option></select></Setting>
          </SettingsSection>}
          {tab === "Interface" && <SettingsSection title="Rendering and interaction">
            <Setting label="Theme"><select value={draft.theme} onChange={event => update("theme", event.target.value as AppSettings["theme"])}><option value="professional-dark">Professional dark</option><option value="high-contrast">High contrast</option><option value="system">Follow system</option></select></Setting>
            <Setting label="Rendering profile"><select value={draft.renderQuality} onChange={event => update("renderQuality", event.target.value as AppSettings["renderQuality"])}><option value="quality">Quality</option><option value="balanced">Balanced</option><option value="performance">Performance</option></select></Setting>
            <Setting label="Maximum frame rate"><select value={draft.maximumFps} onChange={event => update("maximumFps", Number(event.target.value) as AppSettings["maximumFps"])}><option value={30}>30 FPS</option><option value={60}>60 FPS</option><option value={120}>120 FPS</option></select></Setting>
            <Setting label="Antialiasing"><input type="checkbox" checked={draft.antialiasing} onChange={event => update("antialiasing", event.target.checked)} /></Setting>
            <Setting label="Navigation inertia"><input type="checkbox" checked={draft.navigationInertia} onChange={event => update("navigationInertia", event.target.checked)} /></Setting>
            <Setting label="Blink selected objects"><input type="checkbox" checked={draft.selectionBlink} onChange={event => update("selectionBlink", event.target.checked)} /></Setting>
            <Setting label="Show command ribbon"><input type="checkbox" checked={draft.ribbonVisible} onChange={event => update("ribbonVisible", event.target.checked)} /></Setting>
          </SettingsSection>}
          {tab === "Language" && <SettingsSection title="Display language">
            <Setting label="Application language"><select value={draft.language} onChange={event => update("language", event.target.value as AppSettings["language"])}>{Object.entries(LANGUAGE_NAMES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></Setting>
            <p className="settings-note">The localization framework is active for global application commands. Engineering identifiers, net names, units, and solver messages remain unmodified.</p>
          </SettingsSection>}
          {tab === "Profile" && <SettingsSection title="Display profile">
            <Setting label="Display name"><input value={draft.profile.displayName} onChange={event => update("profile", { ...draft.profile, displayName: event.target.value })} /></Setting>
            <p className="settings-note">The display name appears in this local workspace and is saved with interface preferences.</p>
          </SettingsSection>}
          {tab === "Privacy" && <SettingsSection title="Privacy and diagnostics">
            <Setting label="Telemetry"><select value={draft.telemetry} onChange={event => update("telemetry", event.target.value as AppSettings["telemetry"])}><option value="off">Off</option><option value="crash-only">Local crash reports only</option></select></Setting>
            <p className="settings-note">Design files, simulation inputs, and results stay local. No cloud connection is required for the desktop workflow.</p>
          </SettingsSection>}
        </main>
      </div>
      <footer><button className="secondary-btn" onClick={onClose}>Cancel</button><button className="run-btn" onClick={() => onSave(draft)}>Apply settings</button></footer>
    </section>
  </div>;
}

function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) { return <section className="settings-section"><h3>{title}</h3>{children}</section>; }
function Setting({ label, children }: { label: string; children: React.ReactNode }) { return <label className="settings-row"><span>{label}</span>{children}</label>; }
