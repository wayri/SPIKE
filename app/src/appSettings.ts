export type AppLanguage = "en" | "de" | "es" | "fr" | "ja" | "zh-CN";
export type InterfaceMode = "clean" | "classic";
export type UnitSystem = "si" | "engineering" | "imperial";

export type AppSettings = {
  language: AppLanguage;
  unitSystem: UnitSystem;
  coordinateUnit: "mm" | "mil" | "inch";
  temperatureUnit: "C" | "F" | "K";
  significantDigits: number;
  theme: "professional-dark" | "light" | "high-contrast" | "system";
  uiScale: number;
  interfaceMode: InterfaceMode;
  viewportBackground: "dark" | "light" | "amoled";
  viewportGrid: boolean;
  renderQuality: "balanced" | "quality" | "performance";
  maximumFps: 30 | 60 | 120;
  antialiasing: boolean;
  navigationInertia: boolean;
  selectionBlink: boolean;
  ribbonVisible: boolean;
  quickToolsVisible: boolean;
  chromeVersion: 3;
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
  uiScale: 1,
  interfaceMode: "clean",
  viewportBackground: "dark",
  viewportGrid: true,
  renderQuality: "balanced",
  maximumFps: 60,
  antialiasing: true,
  navigationInertia: false,
  selectionBlink: true,
  ribbonVisible: false,
  quickToolsVisible: false,
  chromeVersion: 3,
  extensionUiVisibility: {},
  solverMemoryFraction: 0.65,
  solverMemoryLimitGb: 2,
  restoreWorkspace: true,
  autosaveMinutes: 5,
  telemetry: "off",
  profile: { displayName: "SPIKE User", initials: "USR" },
};

export const APP_SETTINGS_STORAGE_KEY = "spike.application.settings.v1";

export function loadAppSettings(): AppSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(APP_SETTINGS_STORAGE_KEY) ?? "{}") as Partial<AppSettings> & { solverMemoryLimitMb?: number };
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
      // The legacy command ribbon belongs exclusively to Classic layout.
      theme: saved.theme === "light" || saved.theme === "high-contrast" || saved.theme === "system" ? saved.theme : "professional-dark",
      interfaceMode: saved.interfaceMode === "classic" ? "classic" : "clean",
      quickToolsVisible: saved.chromeVersion === 3 && saved.quickToolsVisible === true,
      chromeVersion: 3,
      ribbonVisible: saved.interfaceMode === "classic" && saved.ribbonVisible === true,
      uiScale: typeof saved.uiScale === "number" && Number.isFinite(saved.uiScale) ? Math.max(.65, Math.min(1.5, saved.uiScale)) : 1,
      viewportBackground: saved.viewportBackground === "amoled" ? "amoled" : saved.viewportBackground === "light" ? "light" : "dark",
      viewportGrid: typeof saved.viewportGrid === "boolean" ? saved.viewportGrid : true,
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

export function toggleLegacyRibbon(settings: AppSettings): AppSettings {
  return { ...settings, ribbonVisible: settings.interfaceMode === "classic" && !settings.ribbonVisible };
}

export function saveAppSettings(settings: AppSettings): void {
  try {
    localStorage.setItem(APP_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
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
