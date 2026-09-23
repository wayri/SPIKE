export type AppLanguage = "en" | "de" | "es" | "fr" | "ja" | "zh-CN";
export type UnitSystem = "si" | "engineering" | "imperial";
export type UserType = "viewer" | "engineer" | "administrator" | "developer";
export type LicenseTier = "evaluation" | "professional" | "enterprise" | "developer";

export type AppSettings = {
  language: AppLanguage;
  unitSystem: UnitSystem;
  coordinateUnit: "mm" | "mil" | "inch";
  temperatureUnit: "C" | "F" | "K";
  significantDigits: number;
  theme: "professional-dark" | "high-contrast" | "system";
  renderQuality: "balanced" | "quality" | "performance";
  maximumFps: 30 | 60 | 120;
  antialiasing: boolean;
  navigationInertia: boolean;
  selectionBlink: boolean;
  ribbonVisible: boolean;
  solverMemoryFraction: number;
  solverMemoryLimitGb: number;
  restoreWorkspace: boolean;
  autosaveMinutes: 0 | 1 | 5 | 10 | 30;
  telemetry: "off" | "crash-only";
  profile: { displayName: string; initials: string; userType: UserType };
  license: {
    tier: LicenseTier;
    status: "active" | "expired" | "invalid" | "unlicensed";
    licensee: string;
    source: "signed-license" | "none";
    expiresAt: string | null;
    capabilities: string[];
    licenseId?: string | null;
    licenseType?: "temporary" | "timed" | "perpetual" | "developer" | null;
    deviceBinding?: string;
    errorCode?: string | null;
    message?: string | null;
  };
};

export const ALL_CAPABILITIES = [
  "project.read", "project.write", "design.import", "pi.dc", "pi.ac", "pi.transient",
  "spice.execute", "solver.extensions", "thermal.prepare", "report.export", "step.export",
  "validation.run", "administration.settings",
];

export const DEFAULT_SETTINGS: AppSettings = {
  language: "en",
  unitSystem: "engineering",
  coordinateUnit: "mm",
  temperatureUnit: "C",
  significantDigits: 5,
  theme: "professional-dark",
  renderQuality: "balanced",
  maximumFps: 60,
  antialiasing: true,
  navigationInertia: false,
  selectionBlink: true,
  ribbonVisible: true,
  solverMemoryFraction: 0.65,
  solverMemoryLimitGb: 2,
  restoreWorkspace: true,
  autosaveMinutes: 5,
  telemetry: "off",
  profile: { displayName: "SPIKE User", initials: "USR", userType: "viewer" },
  license: {
    tier: "evaluation",
    status: "unlicensed",
    licensee: "Unlicensed user",
    source: "none",
    expiresAt: null,
    capabilities: ["project.read"],
    licenseId: null,
    licenseType: null,
    errorCode: "SPIKE-BE-SECURITY-E-0005",
    message: "No license is installed",
  },
};

const STORAGE_KEY = "spike.application.settings.v1";

export function loadAppSettings(): AppSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<AppSettings> & { solverMemoryLimitMb?: number };
    const savedLimitGb = Number(saved.solverMemoryLimitGb);
    const legacyLimitMb = Number(saved.solverMemoryLimitMb);
    const solverMemoryLimitGb = Math.max(2,
      Number.isFinite(savedLimitGb) && savedLimitGb > 0
        ? savedLimitGb
        : Number.isFinite(legacyLimitMb) && legacyLimitMb > 0
          ? legacyLimitMb / 1024
          : DEFAULT_SETTINGS.solverMemoryLimitGb,
    );
    return {
      ...DEFAULT_SETTINGS,
      ...saved,
      solverMemoryLimitGb,
      profile: { ...DEFAULT_SETTINGS.profile, ...(saved.profile ?? {}) },
      license: DEFAULT_SETTINGS.license,
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveAppSettings(settings: AppSettings): void {
  const persisted = { ...settings, license: undefined };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
  } catch {
    // Hardened WebViews may deny persistent storage; runtime settings remain usable.
  }
}

export const LANGUAGE_NAMES: Record<AppLanguage, string> = {
  en: "English", de: "Deutsch", es: "Español", fr: "Français", ja: "日本語", "zh-CN": "简体中文",
};

const TRANSLATIONS: Record<AppLanguage, Record<string, string>> = {
  en: { File: "File", Edit: "Edit", View: "View", Project: "Project", Help: "Help", Settings: "Settings", Open: "Open", Save: "Save", Reports: "Reports" },
  de: { File: "Datei", Edit: "Bearbeiten", View: "Ansicht", Project: "Projekt", Help: "Hilfe", Settings: "Einstellungen", Open: "Öffnen", Save: "Speichern", Reports: "Berichte" },
  es: { File: "Archivo", Edit: "Editar", View: "Vista", Project: "Proyecto", Help: "Ayuda", Settings: "Ajustes", Open: "Abrir", Save: "Guardar", Reports: "Informes" },
  fr: { File: "Fichier", Edit: "Modifier", View: "Affichage", Project: "Projet", Help: "Aide", Settings: "Paramètres", Open: "Ouvrir", Save: "Enregistrer", Reports: "Rapports" },
  ja: { File: "ファイル", Edit: "編集", View: "表示", Project: "プロジェクト", Help: "ヘルプ", Settings: "設定", Open: "開く", Save: "保存", Reports: "レポート" },
  "zh-CN": { File: "文件", Edit: "编辑", View: "视图", Project: "项目", Help: "帮助", Settings: "设置", Open: "打开", Save: "保存", Reports: "报告" },
};

export function translate(language: AppLanguage, key: string): string {
  return TRANSLATIONS[language][key] ?? TRANSLATIONS.en[key] ?? key;
}

export function hasCapability(settings: AppSettings, capability: string): boolean {
  return settings.license.status === "active" && (
    settings.license.tier === "developer"
    || settings.license.licenseType === "developer"
    || settings.license.capabilities.includes(capability)
  );
}
