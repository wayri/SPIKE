// SPDX-License-Identifier: Apache-2.0
//! Committed desktop exit and bounded cleanup of SPIKE-owned workers.

use std::process::{Child, ExitStatus};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex, TryLockError};
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;

const CLEANUP_BUDGET: Duration = Duration::from_secs(3);
const EXIT_BUDGET: Duration = Duration::from_secs(5);

#[derive(Default)]
struct State {
    closing: AtomicBool,
    exit_ready: AtomicBool,
    requests: AtomicUsize,
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

    pub(crate) fn admit_update_exit(&self) {
        self.0.closing.store(true, Ordering::SeqCst);
        self.0.exit_ready.store(true, Ordering::SeqCst);
    }

    fn begin(&self) -> bool {
        !self.0.closing.swap(true, Ordering::SeqCst)
    }

    fn idle(&self) -> bool {
        self.0.requests.load(Ordering::SeqCst) == 0
    }
}

pub(crate) fn begin_shutdown(app: tauri::AppHandle) {
    let lifecycle = app.state::<Lifecycle>().inner().clone();
    if !lifecycle.begin() {
        return;
    }
    let resident = app.state::<super::ResidentWorkerState>().0.clone();
    let cleanup_app = app.clone();
    let cleanup_lifecycle = lifecycle.clone();
    let (done, completion) = mpsc::channel();
    thread::spawn(move || {
        cleanup_app.state::<super::mcp_bridge::BridgeState>().stop();
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
        super::close_recovery::retire_owned_children();
        let _ = done.send(());
    });
    thread::spawn(move || {
        let _ = completion.recv_timeout(CLEANUP_BUDGET);
        lifecycle.0.exit_ready.store(true, Ordering::SeqCst);
        app.exit(0);
    });
    thread::spawn(move || {
        thread::sleep(EXIT_BUDGET);
        std::process::exit(0);
    });
}

fn clear_resident<T>(state: &Mutex<Option<T>>) -> bool {
    let worker = match state.try_lock() {
        Ok(mut resident) => resident.take(),
        Err(TryLockError::Poisoned(error)) => error.into_inner().take(),
        Err(TryLockError::WouldBlock) => return false,
    };
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
    fn committed_shutdown_rejects_new_requests_and_drains_existing_requests() {
        let lifecycle = Lifecycle::default();
        let request = lifecycle.enter().unwrap();
        assert!(!lifecycle.idle());
        assert!(lifecycle.begin());
        assert!(!lifecycle.begin());
        assert!(lifecycle.enter().is_err());
        drop(request);
        assert!(lifecycle.idle());
        assert!(!lifecycle.exit_ready());
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
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap()
    }

    #[test]
    fn owned_process_wait_is_bounded() {
        let mut owned = sleeper();
        let started = Instant::now();
        assert!(wait_for_child(&mut owned, Duration::from_millis(30)).is_none());
        super::super::terminate_worker_tree(&mut owned);
        assert!(wait_for_child(&mut owned, Duration::from_secs(2)).is_some());
        assert!(started.elapsed() < Duration::from_secs(5));
    }
}
