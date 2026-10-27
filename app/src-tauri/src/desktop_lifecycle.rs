// SPDX-License-Identifier: Apache-2.0
//! Committed desktop exit and bounded cleanup of SPIKE-owned workers.

use std::process::{Child, ExitStatus};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex, TryLockError};
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;

const DRAIN_BUDGET: Duration = Duration::from_secs(2);
const CLEANUP_BUDGET: Duration = Duration::from_secs(4);
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
    let bridge_app = app.clone();
    let cleanup_lifecycle = lifecycle.clone();
    let completion = start_cleanup(
        move || bridge_app.state::<super::mcp_bridge::BridgeState>().stop(),
        move || {
            drain_and_retire(
                &resident,
                || cleanup_lifecycle.idle(),
                DRAIN_BUDGET,
                super::close_recovery::retire_owned_children,
            );
        },
    );
    thread::spawn(move || {
        exit_after_cleanup(completion, CLEANUP_BUDGET, || {
            lifecycle.0.exit_ready.store(true, Ordering::SeqCst);
            app.exit(0);
        });
    });
    thread::spawn(move || {
        thread::sleep(EXIT_BUDGET);
        std::process::exit(0);
    });
}

/// A contended bridge mutex must not prevent retirement of owned processes.
fn start_cleanup(
    stop_bridge: impl FnOnce() + Send + 'static,
    retire_workers: impl FnOnce() + Send + 'static,
) -> mpsc::Receiver<()> {
    thread::spawn(stop_bridge);
    let (done, completion) = mpsc::channel();
    thread::spawn(move || {
        retire_workers();
        let _ = done.send(());
    });
    completion
}

fn drain_and_retire<T>(
    resident: &Mutex<Option<T>>,
    idle: impl Fn() -> bool,
    drain_budget: Duration,
    retire_children: impl FnOnce(),
) {
    let started = Instant::now();
    loop {
        if clear_resident(resident) && idle() {
            break;
        }
        if started.elapsed() >= drain_budget {
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }
    // Reserve a separate part of the total cleanup budget for this last resort.
    retire_children();
}

fn exit_after_cleanup(
    completion: mpsc::Receiver<()>,
    cleanup_budget: Duration,
    exit: impl FnOnce(),
) {
    let _ = completion.recv_timeout(cleanup_budget);
    exit();
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

    #[test]
    fn exit_waits_for_retirement_even_when_bridge_stop_is_blocked() {
        let (release_bridge, blocked_bridge) = mpsc::channel();
        let (retirement_started, retirement) = mpsc::channel();
        let (release_retirement, blocked_retirement) = mpsc::channel();
        let (exited, exit_observed) = mpsc::channel();
        let completion = start_cleanup(
            move || {
                blocked_bridge.recv().unwrap();
            },
            move || {
                retirement_started.send(()).unwrap();
                blocked_retirement.recv().unwrap();
            },
        );
        let coordinator = thread::spawn(move || {
            exit_after_cleanup(completion, Duration::from_secs(2), || {
                exited.send(()).unwrap()
            });
        });
        retirement.recv_timeout(Duration::from_secs(1)).unwrap();
        assert!(
            matches!(
                exit_observed.recv_timeout(Duration::from_millis(30)),
                Err(mpsc::RecvTimeoutError::Timeout)
            ),
            "normal exit must wait for descendant retirement to finish"
        );
        release_retirement.send(()).unwrap();
        exit_observed.recv_timeout(Duration::from_secs(1)).unwrap();
        // The bridge is still blocked when retirement and normal exit complete.
        release_bridge.send(()).unwrap();
        coordinator.join().unwrap();
    }

    #[test]
    fn locked_resident_cannot_consume_the_retirement_phase() {
        let resident = Arc::new(Mutex::new(Some(1)));
        let locked = resident.lock().unwrap();
        let worker_resident = resident.clone();
        let (retired, retirement) = mpsc::channel();
        let cleanup = thread::spawn(move || {
            drain_and_retire(
                &worker_resident,
                || false,
                Duration::from_millis(20),
                || {
                    retired.send(()).unwrap();
                },
            );
        });
        // The resident stays locked throughout: deadline expiry must still retire.
        retirement.recv_timeout(Duration::from_secs(1)).unwrap();
        drop(locked);
        cleanup.join().unwrap();
    }

    #[test]
    fn stuck_retirement_has_a_bounded_normal_exit_fallback() {
        let (_done, completion) = mpsc::channel::<()>();
        let started = Instant::now();
        let mut exited = false;
        exit_after_cleanup(completion, Duration::from_millis(20), || exited = true);
        assert!(exited);
        assert!(started.elapsed() >= Duration::from_millis(20));
        assert!(started.elapsed() < Duration::from_secs(1));
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
