// SPDX-License-Identifier: Apache-2.0
//! Native hosts for same-origin window.open panels owned by the main React tree.
use std::collections::HashSet;
use std::ffi::OsString;
use std::sync::{Arc, Mutex};
use tauri::{webview::NewWindowResponse, Manager, WebviewUrl, WebviewWindowBuilder};

const MAX_PANEL_POPUPS: usize = 12;
const POPUP_PREFIX: &str = "spike-panel-popup-";
const QUALIFICATION_FLAG: &str = "--panel-popup-qualification";

fn qualification_requested(args: impl IntoIterator<Item = OsString>) -> bool {
    args.into_iter()
        .any(|argument| argument == QUALIFICATION_FLAG)
}

pub(crate) struct PanelWindowState {
    scale: Mutex<f64>,
    registry: Arc<Mutex<PopupRegistry>>,
}

impl Default for PanelWindowState {
    fn default() -> Self {
        Self {
            scale: Mutex::new(1.0),
            registry: Arc::new(Mutex::new(PopupRegistry::default())),
        }
    }
}

fn validate_scale(scale: f64) -> Result<f64, String> {
    if scale.is_finite() && (0.65..=1.5).contains(&scale) {
        Ok(scale)
    } else {
        Err("UI scale must be finite and between 0.65 and 1.5".into())
    }
}

fn trusted_ui_origin(url: &tauri::Url, development: Option<&tauri::Url>) -> bool {
    if !url.username().is_empty() || url.password().is_some() {
        return false;
    }
    (url.scheme() == "tauri" && url.host_str() == Some("localhost") && url.port().is_none())
        || (matches!(url.scheme(), "http" | "https")
            && url.host_str() == Some("tauri.localhost")
            && url.port().is_none())
        || development.is_some_and(|dev| {
            dev.scheme() == "http"
                && matches!(dev.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"))
                && url.origin() == dev.origin()
        })
}

fn trusted_main(label: &str, url: &tauri::Url, development: Option<&tauri::Url>) -> bool {
    label == "main" && trusted_ui_origin(url, development)
}

fn scale_target(
    label: &str,
    url: &tauri::Url,
    owned_popup: bool,
    development: Option<&tauri::Url>,
) -> bool {
    if owned_popup && label.starts_with(POPUP_PREFIX) {
        return blank_document(url);
    }
    matches!(
        label,
        "main"
            | "spike-tool-results"
            | "spike-tool-probes"
            | "spike-tool-trace-plots"
            | "spike-assembly-workspace"
            | "spike-assembly-placement"
            | "spike-assembly-managers"
            | "spike-schematic-viewer"
            | "spike-assistant"
            | "spike-report-preview"
    ) && trusted_ui_origin(url, development)
}

fn development_origin(app: &tauri::AppHandle) -> Option<&tauri::Url> {
    app.config()
        .build
        .dev_url
        .as_ref()
        .filter(|_| cfg!(not(feature = "custom-protocol")))
}

/// Apply saved scale to newly loaded first-party views without enabling keyboard zoom.
pub(crate) fn apply_ui_scale(webview: &tauri::Webview) -> Result<(), String> {
    let app = webview.app_handle();
    let state = app.state::<PanelWindowState>();
    let owned = state
        .registry
        .lock()
        .map_err(|_| "Panel registry unavailable")?
        .labels
        .contains(webview.label());
    let url = webview.url().map_err(|error| error.to_string())?;
    if scale_target(webview.label(), &url, owned, development_origin(app)) {
        let scale = *state.scale.lock().map_err(|_| "Panel scale unavailable")?;
        webview.set_zoom(scale).map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub(crate) fn set_panel_ui_scale(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    scale: f64,
) -> Result<(), String> {
    if !trusted_main(
        window.label(),
        &window.url().map_err(|error| error.to_string())?,
        development_origin(&app),
    ) {
        return Err("UI scale changes require the trusted main application window".into());
    }
    let scale = validate_scale(scale)?;
    *app.state::<PanelWindowState>()
        .scale
        .lock()
        .map_err(|_| "Panel scale unavailable")? = scale;
    let mut failures = Vec::new();
    for (label, view) in app.webview_windows() {
        if let Err(error) = apply_ui_scale(view.as_ref()) {
            failures.push(format!("{label}: {error}"));
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        Err(format!("Could not apply UI scale: {}", failures.join("; ")))
    }
}

fn panel_title(title: &str) -> String {
    let title: String = title
        .chars()
        .filter(|character| !character.is_control())
        .take(120)
        .collect();
    let title = title.trim();
    if title.is_empty() {
        "SPIKE | Tool panel".into()
    } else {
        title.into()
    }
}

fn popup_identity_script(label: &str) -> String {
    format!("if (!Object.prototype.hasOwnProperty.call(window, '__SPIKE_PANEL_WINDOW_LABEL__')) Object.defineProperty(window, '__SPIKE_PANEL_WINDOW_LABEL__', {{ value: {}, writable: false, configurable: false }});", serde_json::json!(label))
}

fn blank_document(url: &tauri::Url) -> bool {
    url.as_str() == "about:blank"
}

#[derive(Default)]
struct PopupRegistry {
    sequence: u64,
    labels: HashSet<String>,
}

impl PopupRegistry {
    fn reserve(&mut self, url: &tauri::Url) -> Option<String> {
        if !blank_document(url) || self.labels.len() >= MAX_PANEL_POPUPS {
            return None;
        }
        self.sequence = self.sequence.checked_add(1)?;
        let label = format!("{POPUP_PREFIX}{}", self.sequence);
        self.labels.insert(label.clone());
        Some(label)
    }

    fn release(&mut self, label: &str) {
        self.labels.remove(label);
    }
}

/// Build the configured main window explicitly so only it may host linked popups.
pub(crate) fn create_main(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let qualification = qualification_requested(std::env::args_os().skip(1));
    let mut config = app
        .config()
        .app
        .windows
        .iter()
        .find(|window| window.label == "main")
        .ok_or("SPIKE main window configuration is missing")?
        .clone();
    if qualification {
        // Tauri resolves this fixed application-relative URL against the current
        // packaged/dev origin before loading scripts. The normal App never mounts.
        config.url = WebviewUrl::App("index.html?panelQualification=1".into());
    }
    let registry = Arc::clone(&app.state::<PanelWindowState>().registry);
    let popup_registry = Arc::clone(&registry);
    let owner = app.handle().clone();
    let mut builder =
        WebviewWindowBuilder::from_config(app, &config)?.on_new_window(move |url, features| {
            let Some(label) = popup_registry
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .reserve(&url)
            else {
                return NewWindowResponse::Deny;
            };
            // NewWindowResponse links this native WebView to window.open's
            // browsing context. Sharing its environment/configuration preserves
            // the opener relationship; an independent child route would not.
            let result = WebviewWindowBuilder::new(&owner, &label, WebviewUrl::External(url))
                .window_features(features)
                // Parent-owned close actions use this SPIKE contract rather than
                // Tauri internals. window.close alone can leave the native frame.
                // The generated label is JSON encoded; no supplied script is run.
                .initialization_script(popup_identity_script(&label))
                .on_page_load(|window, payload| {
                    if payload.event() == tauri::webview::PageLoadEvent::Finished {
                        if let Err(error) = window.eval(&popup_identity_script(window.label())) {
                            eprintln!("Could not bind SPIKE floating window identity: {error}");
                        }
                    }
                })
                .title("SPIKE | Tool panel")
                .min_inner_size(320.0, 240.0)
                .resizable(true)
                .decorations(true)
                .skip_taskbar(false)
                .disable_drag_drop_handler()
                .on_navigation(blank_document)
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .on_document_title_changed(|window, title| {
                    if let Err(error) = window.eval(&popup_identity_script(window.label())) {
                        eprintln!("Could not bind SPIKE floating window identity: {error}");
                    }
                    if let Err(error) = window.set_title(&panel_title(&title)) {
                        eprintln!("Could not update SPIKE tool panel title: {error}");
                    }
                })
                .build();
            match result {
                Ok(window) => {
                    // Blank documents need the policy even before a load event;
                    // the global on_page_load hook also reapplies it on reload.
                    super::webview_policy::apply(window.as_ref());
                    if let Err(error) = apply_ui_scale(window.as_ref()) {
                        eprintln!("Could not scale SPIKE tool panel: {error}");
                    }
                    let child_registry = Arc::clone(&popup_registry);
                    window.on_window_event(move |event| {
                        if matches!(event, tauri::WindowEvent::Destroyed) {
                            child_registry
                                .lock()
                                .unwrap_or_else(|error| error.into_inner())
                                .release(&label);
                        }
                    });
                    NewWindowResponse::Create { window }
                }
                Err(error) => {
                    popup_registry
                        .lock()
                        .unwrap_or_else(|error| error.into_inner())
                        .release(&label);
                    eprintln!("Could not create SPIKE tool panel window: {error}");
                    NewWindowResponse::Deny
                }
            }
        });
    if qualification {
        builder = builder.on_document_title_changed(|window, title| {
            // A desktop process may expose its focused child as MainWindowTitle.
            // Keep the bounded diagnostic status observable without UI automation.
            eprintln!("SPIKE panel qualification title: {}", panel_title(&title));
            if let Err(error) = window.set_title(&panel_title(&title)) {
                eprintln!("Could not expose SPIKE panel qualification status: {error}");
            }
        });
    }
    let main = builder.build()?;
    let owner = app.handle().clone();
    main.on_window_event(move |event| {
        if matches!(event, tauri::WindowEvent::Destroyed) {
            // Normal Close still goes through close_recovery and the frontend's
            // dirty-state checks. Retire children if the owning window is gone.
            let labels: Vec<_> = registry
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .labels
                .iter()
                .cloned()
                .collect();
            for label in labels {
                if let Some(child) = owner.get_webview_window(&label) {
                    if let Err(error) = child.destroy() {
                        eprintln!("Could not retire SPIKE tool panel {label}: {error}");
                    }
                }
            }
        }
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn qualification_flag_requires_an_exact_standalone_argument() {
        assert!(qualification_requested([OsString::from(
            QUALIFICATION_FLAG
        )]));
        assert!(!qualification_requested(Vec::<OsString>::new()));
        for argument in [
            "--panel-popup-qualification=1",
            "--panel-popup-qualification=https://example.com/",
            "--panel-popup-qualification ",
            "--PANEL-POPUP-QUALIFICATION",
            "--panel-popup-qualification\n",
            "prefix--panel-popup-qualification",
        ] {
            assert!(
                !qualification_requested([OsString::from(argument)]),
                "{argument}"
            );
        }
    }

    #[test]
    fn scale_accepts_only_finite_supported_values() {
        for value in [0.65, 1.0, 1.5] {
            assert_eq!(validate_scale(value).unwrap(), value);
        }
        for value in [
            f64::NAN,
            f64::INFINITY,
            f64::NEG_INFINITY,
            0.0,
            0.649,
            1.501,
        ] {
            assert!(validate_scale(value).is_err());
        }
    }

    #[test]
    fn scale_requires_main_identity_and_trusted_origin() {
        let dev = "http://127.0.0.1:1420/".parse().unwrap();
        let packaged = "http://tauri.localhost/index.html".parse().unwrap();
        assert!(trusted_main("main", &packaged, None));
        assert!(trusted_main(
            "main",
            &"tauri://localhost/index.html".parse().unwrap(),
            None
        ));
        assert!(trusted_main("main", &dev, Some(&dev)));
        assert!(!trusted_main("main", &dev, None));
        assert!(!trusted_main("spike-panel-popup-1", &packaged, None));
        for source in [
            "about:blank",
            "https://example.com",
            "http://127.0.0.1:1421/",
            "http://localhost:1420/",
            "http://user@tauri.localhost/",
            "http://tauri.localhost:8080/",
        ] {
            assert!(
                !trusted_main("main", &source.parse().unwrap(), Some(&dev)),
                "{source}"
            );
        }
    }

    #[test]
    fn scale_targets_known_local_views_and_registered_blank_popups_only() {
        let blank = "about:blank".parse().unwrap();
        let local = "http://tauri.localhost/index.html".parse().unwrap();
        assert!(scale_target("spike-tool-results", &local, false, None));
        assert!(!scale_target("unregistered-window", &local, false, None));
        assert!(scale_target("spike-panel-popup-1", &blank, true, None));
        assert!(!scale_target("spike-panel-popup-1", &blank, false, None));
        assert!(!scale_target("spike-panel-popup-1", &local, true, None));
        assert!(!scale_target(
            "spike-tool-results",
            &"https://example.com".parse().unwrap(),
            false,
            None
        ));
    }

    #[test]
    fn document_titles_are_bounded_and_controls_removed() {
        assert_eq!(panel_title("\n\t"), "SPIKE | Tool panel");
        assert_eq!(panel_title("  SPIKE | Layers\n"), "SPIKE | Layers");
        assert_eq!(panel_title(&"a".repeat(200)).chars().count(), 120);
    }

    #[test]
    fn only_exact_blank_document_is_admitted() {
        assert!(blank_document(&"about:blank".parse().unwrap()));
        for source in [
            "about:blank#panel",
            "about:blank?panel=1",
            "about:srcdoc",
            "https://example.com/",
            "http://127.0.0.1:1420/",
            "tauri://localhost/",
            "file:///C:/panel.html",
            "data:text/html,panel",
            "javascript:alert(1)",
        ] {
            assert!(!blank_document(&source.parse().unwrap()), "{source}");
        }
    }

    #[test]
    fn reservations_are_bounded_and_released_without_reusing_labels() {
        let mut registry = PopupRegistry::default();
        let blank = "about:blank".parse().unwrap();
        let labels: Vec<_> = (0..MAX_PANEL_POPUPS)
            .map(|_| registry.reserve(&blank).unwrap())
            .collect();
        assert!(registry.reserve(&blank).is_none());
        registry.release(&labels[0]);
        let replacement = registry.reserve(&blank).unwrap();
        assert!(!labels.contains(&replacement));
        assert!(registry.reserve(&blank).is_none());
        // Repeated destruction/failure cleanup cannot free another reservation.
        registry.release(&labels[0]);
        assert!(registry.reserve(&blank).is_none());
    }

    #[test]
    fn rejected_urls_and_exhausted_ids_do_not_reserve_slots() {
        let mut registry = PopupRegistry::default();
        assert!(registry
            .reserve(&"https://example.com".parse().unwrap())
            .is_none());
        assert!(registry.labels.is_empty());
        assert_eq!(registry.sequence, 0);
        registry.sequence = u64::MAX;
        assert!(registry.reserve(&"about:blank".parse().unwrap()).is_none());
        assert!(registry.labels.is_empty());
    }
}
