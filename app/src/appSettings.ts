export type AppLanguage = "en" | "de" | "es" | "fr" | "ja" | "zh-CN";
export type UnitSystem = "si" | "engineering" | "imperial";

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
  extensionUiVisibility: Record<string, { menuBar: boolean; titleBar: boolean }>;
  solverMemoryFraction: number;
  solverMemoryLimitGb: number;
  restoreWorkspace: boolean;
  autosaveMinutes: 0 | 1 | 5 | 10 | 30;
  telemetry: "off" | "crash-only";
  profile: { displayName: string; initials: string };
};

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
  extensionUiVisibility: {},
  solverMemoryFraction: 0.65,
  solverMemoryLimitGb: 2,
  restoreWorkspace: true,
  autosaveMinutes: 5,
  telemetry: "off",
  profile: { displayName: "SPIKE User", initials: "USR" },
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
    const known = Object.fromEntries(Object.keys(DEFAULT_SETTINGS)
      .filter(key => key in saved)
      .map(key => [key, saved[key as keyof AppSettings]])) as Partial<AppSettings>;
    return {
      ...DEFAULT_SETTINGS,
      ...known,
      solverMemoryLimitGb,
      profile: {
        displayName: typeof saved.profile?.displayName === "string" ? saved.profile.displayName : DEFAULT_SETTINGS.profile.displayName,
        initials: typeof saved.profile?.initials === "string" ? saved.profile.initials : DEFAULT_SETTINGS.profile.initials,
      },
      extensionUiVisibility: saved.extensionUiVisibility && typeof saved.extensionUiVisibility === "object" && !Array.isArray(saved.extensionUiVisibility)
        ? saved.extensionUiVisibility : {},
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveAppSettings(settings: AppSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
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
