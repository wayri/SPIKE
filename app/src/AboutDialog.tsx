import { BookOpen, CircleCheck, Gauge, Info, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { AppSettings } from "./appSettings";
import { APP_VERSION, PRODUCT_NAME, PRODUCT_TAGLINE, RELEASE_CHANNEL } from "./appVersion";
import { getDesktopAppVersion } from "./workerBridge";

type AboutDialogProps = {
  license: AppSettings["license"];
  onClose: () => void;
  onOpenGuide: () => void;
  onOpenValidation: () => void;
};

function formatExpiry(value: string | null): string {
  if (!value) return "no expiry";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return `expires ${parsed.toLocaleDateString()}`;
}

export default function AboutDialog({ license, onClose, onOpenGuide, onOpenValidation }: AboutDialogProps) {
  const [hostVersion, setHostVersion] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getDesktopAppVersion()
      .then(version => { if (active) setHostVersion(version); })
      .catch(() => { /* browser preview has no native host */ });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);

  const statusTone = license.status === "active" ? "" : license.status === "expired" ? "warn" : "error";
  const runtimeLine = hostVersion
    ? "Native desktop shell"
    : "Browser preview · desktop host not detected";
  const platform = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform ?? navigator.platform ?? "unknown platform";

  return <div className="modal-shade about-shade" role="dialog" aria-modal="true" aria-label={`About ${PRODUCT_NAME}`}>
    <section className="about-dialog">
      <header>
        <div>
          <img src="/spike-mark.svg" alt="" />
          <span><b>{PRODUCT_NAME}</b><small>{PRODUCT_TAGLINE}</small></span>
        </div>
        <button className="canvas-icon" onClick={onClose} aria-label="Close about dialog"><X size={16} /></button>
      </header>
      <div className="about-body">
        <div className="about-hero">
          <span className="about-version">v{hostVersion ?? APP_VERSION}</span>
          <span className="about-channel">{RELEASE_CHANNEL.toUpperCase()} channel</span>
          <span className="about-offline"><CircleCheck size={11} /> Offline-first</span>
          <small className="about-runtime">{runtimeLine} · {platform}</small>
        </div>
        <div className="about-license">
          <div className={`license-card ${statusTone}`}>
            <ShieldAlert size={18} />
            <div>
              <b>{license.tier.charAt(0).toUpperCase() + license.tier.slice(1)} tier · {license.status}</b>
              <span>{license.status === "active" ? `${license.licensee} · ${formatExpiry(license.expiresAt)}${license.licenseType ? ` · ${license.licenseType}` : ""}` : (license.message ?? "No entitlement is installed")}</span>
              {license.capabilities.length > 0 && <span>{license.capabilities.length} capabilit{license.capabilities.length === 1 ? "y" : "ies"} granted{license.source === "signed-license" ? " · signed entitlement" : ""}</span>}
            </div>
          </div>
        </div>
        <div className="about-grid" role="table" aria-label="Runtime information">
          <span>Interface</span><b>React + Three.js workspace · offline Tauri host</b>
          <span>Solver worker</span><b>Local Python / C++ analysis service (versioned JSON contracts)</b>
          <span>Native engines</span><b>ngspice 46 · openEMS · OpenFOAM (optional, capability-gated)</b>
          <span>Validation state</span><b>Per-solver notices travel with every result; approximate and experimental modes stay labeled</b>
          <span>Error catalog</span><b>docs/ERROR_CODE_CATALOG.md ships with the installation</b>
        </div>
        <p className="about-note"><b>Numerical validity:</b> the version shown here does not change a solver's validation state. Approximate, experimental, and reference-only capabilities remain labeled as such inside analyses, results, and exported reports.</p>
        <div className="about-links">
          <button onClick={onOpenGuide}><BookOpen size={12} /> Help and user guide</button>
          <button onClick={onOpenValidation}><Gauge size={12} /> Accuracy and validation</button>
        </div>
      </div>
      <footer>
        <span><Info size={11} /> {PRODUCT_NAME} is provided under its packaged license terms; third-party engine licenses are listed in External engines.</span>
        <button className="secondary-btn" onClick={onClose}>Close</button>
      </footer>
    </section>
  </div>;
}
