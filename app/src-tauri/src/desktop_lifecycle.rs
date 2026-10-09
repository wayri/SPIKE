// SPDX-License-Identifier: Apache-2.0
//! Committed desktop exit and bounded cleanup of SPIKE-owned workers.

use std::process::{Child, ExitStatus};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex, TryLockError};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};

const CLEANUP_BUDGET: Duration = Duration::from_secs(3);
const EXIT_BUDGET: Duration = Duration::from_secs(5);
const CLOSE_ACK_BUDGET: Duration = Duration::from_secs(3);
const CLOSE_REQUEST_EVENT: &str = "spike://desktop-close-requested";

// Low three bits encode the stage; high bits identify a particular close attempt.
const CLOSE_IDLE: u64 = 0;
const CLOSE_PENDING: u64 = 1;
const CLOSE_ACKNOWLEDGED: u64 = 2;
const CLOSE_DIALOG: u64 = 3;
const CLOSE_DIALOG_ACKNOWLEDGED: u64 = 4;

#[derive(Default)]
struct CloseRecovery(AtomicU64);

impl CloseRecovery {
    fn request(&self) -> Option<u64> {
        let mut current = self.0.load(Ordering::SeqCst);
        loop {
            if matches!(
                current & 7,
                CLOSE_PENDING | CLOSE_DIALOG | CLOSE_DIALOG_ACKNOWLEDGED
            ) {
                return None;
            }
            let generation = (current >> 3) + 1;
            match self.0.compare_exchange(
                current,
                (generation << 3) | CLOSE_PENDING,
                Ordering::SeqCst,
                Ordering::SeqCst,
            ) {
                Ok(_) => return Some(generation),
                Err(observed) => current = observed,
            }
        }
    }

    fn acknowledge(&self, generation: u64) -> bool {
        self.transition(generation, CLOSE_PENDING, CLOSE_ACKNOWLEDGED)
            || self.transition(generation, CLOSE_DIALOG, CLOSE_DIALOG_ACKNOWLEDGED)
    }

    fn show_dialog(&self, generation: u64) -> bool {
        self.transition(generation, CLOSE_PENDING, CLOSE_DIALOG)
    }

    fn finish_dialog(&self, generation: u64, confirmed: bool) -> bool {
        let mut current = self.0.load(Ordering::SeqCst);
        loop {
            if current >> 3 != generation {
                return false;
            }
            let next = match current & 7 {
                CLOSE_DIALOG => CLOSE_IDLE,
                CLOSE_DIALOG_ACKNOWLEDGED => CLOSE_ACKNOWLEDGED,
                _ => return false,
            };
            match self.0.compare_exchange(
                current,
                (generation << 3) | next,
                Ordering::SeqCst,
                Ordering::SeqCst,
            ) {
                Ok(_) => return next == CLOSE_IDLE && confirmed,
                Err(observed) => current = observed,
            }
        }
    }

    fn transition(&self, generation: u64, from: u64, to: u64) -> bool {
        if generation == 0 || generation > (u64::MAX >> 3) {
            return false;
        }
        self.0
            .compare_exchange(
                (generation << 3) | from,
                (generation << 3) | to,
                Ordering::SeqCst,
                Ordering::SeqCst,
            )
            .is_ok()
    }
}

#[derive(Default)]
struct State {
    closing: AtomicBool,
    exit_ready: AtomicBool,
    requests: AtomicUsize,
    close_recovery: CloseRecovery,
}

#[derive(Clone, Default)]
pub(crate) struct Lifecycle(Arc<State>);

pub(crate) struct RequestGuard(Arc<State>);

impl Drop for RequestGuard {
    fn drop(&mut self) {
        self.0.requests.fetch_sub(1, Ordering::SeqCst);
    }
}

impl Lifecycle {
    pub(crate) fn enter(&self) -> Result<RequestGuard, String> {
        self.0.requests.fetch_add(1, Ordering::SeqCst);
        let guard = RequestGuard(self.0.clone());
        if self.is_closing() {
            return Err("SPIKE is closing; new worker requests are disabled".to_string());
        }
        Ok(guard)
    }

    pub(crate) fn is_closing(&self) -> bool {
        self.0.closing.load(Ordering::SeqCst)
    }

    pub(crate) fn exit_ready(&self) -> bool {
        self.0.exit_ready.load(Ordering::SeqCst)
    }

    fn begin(&self) -> bool {
        !self.0.closing.swap(true, Ordering::SeqCst)
    }

    fn idle(&self) -> bool {
        self.0.requests.load(Ordering::SeqCst) == 0
    }
}

fn require_main_window(label: &str) -> Result<(), String> {
    if label != "main" {
        return Err("Only the main SPIKE workspace may close the application".to_string());
    }
    Ok(())
}

#[derive(Clone, serde::Serialize)]
struct CloseRequest {
    generation: u64,
}

/// Raw native close is always held until either the renderer's normal save/
/// discard guard commits exit or the user explicitly accepts native recovery.
pub(crate) fn on_main_close_requested(window: &tauri::Window) {
    let app = window.app_handle().clone();
    let lifecycle = app.state::<Lifecycle>().inner().clone();
    if lifecycle.is_closing() {
        return;
    }
    let Some(generation) = lifecycle.0.close_recovery.request() else {
        return;
    };
    // Use a separate, generation-bearing event: Tauri emits its ordinary close
    // event before calling the native window handler, so an ACK of that event
    // could otherwise arrive before this request was registered.
    let _ = window.emit(CLOSE_REQUEST_EVENT, CloseRequest { generation });
    let window = window.clone();
    thread::spawn(move || {
        thread::sleep(CLOSE_ACK_BUDGET);
        if lifecycle.is_closing() || !lifecycle.0.close_recovery.show_dialog(generation) {
            return;
        }
        let response = rfd::MessageDialog::new()
            .set_parent(&window)
            .set_title("SPIKE is not responding")
            .set_description("The workspace did not respond to the close request. Unsaved changes may be lost if you close anyway. Close SPIKE and stop its running workers?\n\nChoose No to keep SPIKE open and wait for the workspace to recover.")
            .set_level(rfd::MessageLevel::Warning)
            .set_buttons(rfd::MessageButtons::YesNo)
            .show();
        if lifecycle
            .0
            .close_recovery
            .finish_dialog(generation, response == rfd::MessageDialogResult::Yes)
        {
            begin_shutdown(app);
        }
    });
}

#[tauri::command]
pub(crate) fn acknowledge_desktop_close(
    window: tauri::WebviewWindow,
    generation: u64,
    lifecycle: tauri::State<'_, Lifecycle>,
) -> Result<bool, String> {
    require_main_window(window.label())?;
    Ok(!lifecycle.is_closing() && lifecycle.0.close_recovery.acknowledge(generation))
}

/// Called only after the renderer has completed its save/discard guard.
#[tauri::command]
pub(crate) fn close_desktop_app(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
) -> Result<(), String> {
    require_main_window(window.label())?;
    begin_shutdown(app);
    Ok(())
}

pub(crate) fn begin_shutdown(app: tauri::AppHandle) {
    let lifecycle = app.state::<Lifecycle>().inner().clone();
    if !lifecycle.begin() {
        return;
    }
    // No native mutex is acquired on the webview/event-loop thread. The flag
    // above also cancels lightweight requests that have no ActiveWorker entry.
    let resident = app.state::<super::ResidentWorkerState>().0.clone();
    let cleanup_app = app.clone();
    let cleanup_lifecycle = lifecycle.clone();
    let (done, completion) = mpsc::channel();
    thread::spawn(move || {
        let started = Instant::now();
        loop {
            if clear_resident(&resident) && cleanup_lifecycle.idle() {
                break;
            }
            if started.elapsed() >= CLEANUP_BUDGET {
                break;
            }
            thread::sleep(Duration::from_millis(20));
        }
        cleanup_app.state::<super::mcp_bridge::BridgeState>().stop();
        let _ = done.send(());
    });
    thread::spawn(move || {
        let _ = completion.recv_timeout(CLEANUP_BUDGET);
        lifecycle.0.exit_ready.store(true, Ordering::SeqCst);
        // Exits the entire native application, including detached tool/report
        // windows. Tauri's normal run loop exits the process after cleanup.
        app.exit(0);
    });
    thread::spawn(move || {
        thread::sleep(EXIT_BUDGET);
        // Last resort for a stuck native event loop after the user committed
        // close. This exits only this SPIKE process, never unrelated processes.
        std::process::exit(0);
    });
}

fn clear_resident<T>(state: &Mutex<Option<T>>) -> bool {
    let worker = match state.try_lock() {
        Ok(mut resident) => resident.take(),
        Err(TryLockError::Poisoned(error)) => error.into_inner().take(),
        Err(TryLockError::WouldBlock) => return false,
    };
    // Drop outside the mutex. ResidentWorker terminates its owned process tree.
    drop(worker);
    true
}

pub(crate) fn wait_for_child(child: &mut Child, budget: Duration) -> Option<ExitStatus> {
    let deadline = Instant::now() + budget;
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return Some(status),
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(10)),
            _ => return None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::{Command, Stdio};

    #[test]
    fn close_acknowledgement_suppresses_only_its_own_recovery() {
        let recovery = CloseRecovery::default();
        let first = recovery.request().unwrap();
        assert!(recovery.acknowledge(first));
        assert!(!recovery.show_dialog(first));
        let second = recovery.request().unwrap();
        assert_ne!(first, second);
        assert!(!recovery.acknowledge(first));
        assert!(!recovery.show_dialog(first));
        assert!(recovery.show_dialog(second));
    }

    #[test]
    fn repeated_close_keeps_one_watchdog_and_one_dialog() {
        let recovery = CloseRecovery::default();
        let generation = recovery.request().unwrap();
        assert!(recovery.request().is_none());
        assert!(recovery.show_dialog(generation));
        assert!(recovery.request().is_none());
        assert!(!recovery.show_dialog(generation));
        assert!(!recovery.finish_dialog(generation, false));
        let next = recovery.request().unwrap();
        assert_ne!(generation, next);
        assert!(!recovery.finish_dialog(generation, true));
    }

    #[test]
    fn renderer_recovery_invalidates_native_confirmation_without_duplicate_dialogs() {
        let recovery = CloseRecovery::default();
        let generation = recovery.request().unwrap();
        assert!(recovery.show_dialog(generation));
        assert!(recovery.acknowledge(generation));
        assert!(recovery.request().is_none());
        assert!(!recovery.finish_dialog(generation, true));
        let next = recovery.request().unwrap();
        assert_ne!(generation, next);
        assert!(!recovery.finish_dialog(generation, false));
        assert!(recovery.acknowledge(next));
    }

    #[test]
    fn concurrent_recovery_and_confirmation_leave_no_stuck_dialog() {
        for _ in 0..32 {
            let recovery = Arc::new(CloseRecovery::default());
            let generation = recovery.request().unwrap();
            assert!(recovery.show_dialog(generation));
            let barrier = Arc::new(std::sync::Barrier::new(2));
            let renderer = recovery.clone();
            let ready = barrier.clone();
            let acknowledged = thread::spawn(move || {
                ready.wait();
                renderer.acknowledge(generation)
            });
            barrier.wait();
            let confirmed = recovery.finish_dialog(generation, true);
            assert_ne!(acknowledged.join().unwrap(), confirmed);
            assert!(recovery.request().is_some());
        }
    }

    #[test]
    fn recovery_requires_explicit_confirmation_of_the_live_dialog() {
        let recovery = CloseRecovery::default();
        let generation = recovery.request().unwrap();
        assert!(!recovery.finish_dialog(generation, true));
        assert!(recovery.show_dialog(generation));
        assert!(recovery.finish_dialog(generation, true));
        assert!(!recovery.finish_dialog(generation, true));
    }

    #[test]
    fn committed_shutdown_rejects_new_requests_and_drains_existing_requests() {
        let lifecycle = Lifecycle::default();
        let request = lifecycle.enter().unwrap();
        assert!(!lifecycle.idle());
        assert!(lifecycle.begin());
        assert!(!lifecycle.begin());
        assert!(lifecycle.enter().is_err());
        assert!(!lifecycle.idle());
        drop(request);
        assert!(lifecycle.idle());
        assert!(!lifecycle.exit_ready());
    }

    #[test]
    fn detached_windows_cannot_commit_application_exit() {
        assert!(require_main_window("main").is_ok());
        for label in ["report-preview", "assembly-tools", "results", ""] {
            assert!(require_main_window(label).is_err());
        }
    }

    #[test]
    fn busy_resident_cleanup_never_waits_for_request_mutex() {
        let state = Mutex::new(Some(1));
        let locked = state.lock().unwrap();
        let started = Instant::now();
        assert!(!clear_resident(&state));
        assert!(started.elapsed() < Duration::from_millis(100));
        drop(locked);
        assert!(clear_resident(&state));
        assert!(state.lock().unwrap().is_none());
    }

    fn sleeper() -> Child {
        #[cfg(target_os = "windows")]
        let mut command = {
            use std::os::windows::process::CommandExt;
            let mut command = Command::new("powershell");
            command.args(["-NoProfile", "-Command", "Start-Sleep -Seconds 30"]);
            command.creation_flags(super::super::CREATE_NO_WINDOW);
            command
        };
        #[cfg(not(target_os = "windows"))]
        let mut command = {
            let mut command = Command::new("sleep");
            command.arg("30");
            command
        };
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap()
    }

    #[test]
    fn committed_shutdown_cancels_busy_resident_without_operation_flag() {
        let lifecycle = Lifecycle::default();
        let mut child = sleeper();
        let stdin = child.stdin.take();
        let (_response_sender, responses) = mpsc::channel();
        let (_stderr_sender, stderr) = mpsc::channel();
        let resident = Arc::new(Mutex::new(Some(super::super::ResidentWorker {
            child,
            stdin,
            responses,
            stderr,
        })));
        let shutdown = lifecycle.clone();
        let closer = thread::spawn(move || {
            thread::sleep(Duration::from_millis(100));
            shutdown.begin();
        });
        let started = Instant::now();
        // The child never reads this oversized pipe write or replies. Close
        // must interrupt it even without a heavy-operation cancellation flag.
        let response = super::super::run_resident_worker_request(
            std::path::Path::new("."),
            &resident,
            serde_json::json!({"id": "shutdown-test", "method": "spikes_session_step",
                "params": {"payload": "x".repeat(1024 * 1024)}}),
            None,
            &lifecycle,
        );
        closer.join().unwrap();
        assert!(response.unwrap_err().contains("cancelled"));
        assert!(resident.lock().unwrap().is_none());
        assert!(started.elapsed() < Duration::from_secs(3));
    }

    #[test]
    fn owned_process_cleanup_is_bounded_and_preserves_unrelated_process() {
        let mut owned = sleeper();
        let mut unrelated = sleeper();
        let started = Instant::now();
        assert!(wait_for_child(&mut owned, Duration::from_millis(30)).is_none());
        super::super::terminate_worker_tree(&mut owned);
        let terminated = wait_for_child(&mut owned, Duration::from_secs(2)).is_some();
        let unrelated_alive = unrelated.try_wait().unwrap().is_none();
        super::super::terminate_worker_tree(&mut unrelated);
        let _ = wait_for_child(&mut unrelated, Duration::from_secs(2));
        assert!(terminated);
        assert!(unrelated_alive);
        assert!(started.elapsed() < Duration::from_secs(5));
    }
}
