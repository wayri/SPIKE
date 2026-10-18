// SPDX-License-Identifier: Apache-2.0
//! Native close handshake: renderer failure cannot strand the application's Close button.
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::Duration;
#[cfg(target_os = "windows")]
use sysinfo::{ProcessRefreshKind, ProcessesToUpdate, System};
use tauri::{Emitter, Manager};
const RESPONSE_TIMEOUT: Duration = Duration::from_secs(5);
#[derive(Default)]
pub(crate) struct CloseRecoveryState(Mutex<CloseGate>);
#[derive(Default)]
struct CloseGate {
    sequence: u64,
    pending: Option<u64>,
    dialog: bool,
    closing: bool,
}
impl CloseGate {
    fn request(&mut self) -> Option<(u64, bool)> {
        if self.closing || self.dialog {
            return None;
        }
        if let Some(id) = self.pending {
            return Some((id, false));
        }
        self.sequence = self.sequence.saturating_add(1);
        self.pending = Some(self.sequence);
        Some((self.sequence, true))
    }
    fn respond(&mut self, id: u64) -> bool {
        if self.pending != Some(id) || self.dialog || self.closing {
            return false;
        }
        self.pending = None;
        true
    }
    fn recover(&mut self, id: u64) -> bool {
        if self.pending != Some(id) || self.dialog || self.closing {
            return false;
        }
        self.pending = None;
        self.dialog = true;
        true
    }
    fn keep_open(&mut self) {
        self.dialog = false;
    }
    fn close(&mut self) -> bool {
        if self.closing {
            return false;
        }
        self.closing = true;
        self.pending = None;
        self.dialog = false;
        true
    }
}
fn main_only(window: &tauri::Window) -> Result<(), String> {
    if window.label() == "main" {
        Ok(())
    } else {
        Err("Only the main workspace may approve application shutdown".into())
    }
}
#[tauri::command]
pub(crate) fn main_close_recovery_supported(window: tauri::Window) -> Result<bool, String> {
    main_only(&window)?;
    Ok(true)
}
#[tauri::command]
pub(crate) fn respond_main_close(
    window: tauri::Window,
    app: tauri::AppHandle,
    request_id: u64,
    decision: String,
) -> Result<(), String> {
    main_only(&window)?;
    if !matches!(decision.as_str(), "defer" | "close") {
        return Err("Invalid close response".into());
    }
    let accepted = app
        .state::<CloseRecoveryState>()
        .0
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .respond(request_id);
    if accepted && decision == "close" {
        commit_shutdown(&app);
    }
    Ok(())
}
#[tauri::command]
pub(crate) fn close_main_application(
    window: tauri::Window,
    app: tauri::AppHandle,
) -> Result<(), String> {
    main_only(&window)?;
    commit_shutdown(&app);
    Ok(())
}
pub(crate) fn on_window_event(window: &tauri::Window, event: &tauri::WindowEvent) {
    if window.label() != "main" {
        return;
    }
    let tauri::WindowEvent::CloseRequested { api, .. } = event else {
        return;
    };
    api.prevent_close();
    let app = window.app_handle().clone();
    let Some((id, start_timer)) = app
        .state::<CloseRecoveryState>()
        .0
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .request()
    else {
        return;
    };
    let _ = window.emit(
        "spike:main-close-requested",
        serde_json::json!({"requestId":id}),
    );
    if !start_timer {
        return;
    }
    std::thread::spawn(move || {
        std::thread::sleep(RESPONSE_TIMEOUT);
        if !app
            .state::<CloseRecoveryState>()
            .0
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .recover(id)
        {
            return;
        }
        let response=rfd::MessageDialog::new().set_title("SPIKE is not responding to Close")
   .set_description("The workspace did not respond to the Close button. You can keep waiting, or close SPIKE and its owned simulation processes. Unsaved changes may be lost. Saved projects and completed result files are retained.")
   .set_level(rfd::MessageLevel::Warning)
   .set_buttons(rfd::MessageButtons::OkCancelCustom("Force close SPIKE".into(),"Keep open".into())).show();
        if response == rfd::MessageDialogResult::Custom("Force close SPIKE".into()) {
            commit_shutdown(&app);
        } else {
            app.state::<CloseRecoveryState>()
                .0
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .keep_open();
        }
    });
}
/// Walk only this application's descendant tree; never kill by executable name.
fn descendants(root: u32, parents: &HashMap<u32, u32>) -> Vec<u32> {
    let mut seen = HashSet::from([root]);
    let mut frontier = vec![root];
    let mut found = Vec::new();
    while let Some(parent) = frontier.pop() {
        for (&pid, &owner) in parents {
            if owner == parent && seen.insert(pid) {
                found.push(pid);
                frontier.push(pid);
            }
        }
    }
    found.reverse();
    found
}
#[cfg(target_os = "windows")]
pub(crate) fn retire_owned_children() {
    use native_process::{identity_edges, OwnedHandle};
    let mut system = System::new();
    system.refresh_processes_specifics(ProcessesToUpdate::All, true, ProcessRefreshKind::nothing());
    let parents = system
        .processes()
        .iter()
        .filter_map(|(pid, p)| p.parent().map(|parent| (pid.as_u32(), parent.as_u32())))
        .collect();
    let root = std::process::id();
    let Some(root_handle) = OwnedHandle::open(root, false) else {
        return;
    };
    let mut handles = HashMap::from([(root, root_handle)]);
    for pid in descendants(root, &parents) {
        if let Some(handle) = OwnedHandle::open(pid, true) {
            handles.insert(pid, handle);
        }
    }
    // Reobserve parent identities while handles pin the specific process objects.
    system.refresh_processes_specifics(ProcessesToUpdate::All, true, ProcessRefreshKind::nothing());
    let current_parents = system
        .processes()
        .iter()
        .filter_map(|(pid, p)| p.parent().map(|parent| (pid.as_u32(), parent.as_u32())))
        .collect();
    let starts = handles
        .iter()
        .map(|(pid, handle)| (*pid, handle.created))
        .collect();
    for pid in descendants(root, &identity_edges(&current_parents, &starts)) {
        if let Some(handle) = handles.get(&pid) {
            handle.terminate();
        }
    }
}
#[cfg(not(target_os = "windows"))]
pub(crate) fn retire_owned_children() {}

fn commit_shutdown(app: &tauri::AppHandle) {
    app.state::<CloseRecoveryState>()
        .0
        .lock()
        .unwrap_or_else(|error| error.into_inner())
        .close();
    super::desktop_lifecycle::begin_shutdown(app.clone());
}
#[cfg(any(target_os = "windows", test))]
mod native_process {
    use std::collections::HashMap;
    /// A reused parent PID cannot own a process created before that parent object.
    pub(super) fn identity_edges(
        parents: &HashMap<u32, u32>,
        starts: &HashMap<u32, u64>,
    ) -> HashMap<u32, u32> {
        parents
            .iter()
            .filter_map(
                |(&child, &parent)| match (starts.get(&child), starts.get(&parent)) {
                    (Some(c), Some(p)) if c >= p => Some((child, parent)),
                    _ => None,
                },
            )
            .collect()
    }
    #[cfg(target_os = "windows")]
    mod windows {
        use std::ffi::c_void;
        #[repr(C)]
        #[derive(Default)]
        struct FileTime {
            low: u32,
            high: u32,
        }
        #[link(name = "kernel32")]
        extern "system" {
            fn OpenProcess(access: u32, inherit: i32, pid: u32) -> *mut c_void;
            fn GetProcessTimes(
                handle: *mut c_void,
                created: *mut FileTime,
                exit: *mut FileTime,
                kernel: *mut FileTime,
                user: *mut FileTime,
            ) -> i32;
            fn TerminateProcess(handle: *mut c_void, code: u32) -> i32;
            fn CloseHandle(handle: *mut c_void) -> i32;
        }
        pub(crate) struct OwnedHandle {
            handle: *mut c_void,
            pub(crate) created: u64,
        }
        impl OwnedHandle {
            pub(crate) fn open(pid: u32, terminate: bool) -> Option<Self> {
                // Query + terminate access only; handles are not inherited by children.
                let handle = unsafe { OpenProcess(0x1000 | if terminate { 1 } else { 0 }, 0, pid) };
                if handle.is_null() {
                    return None;
                }
                let (mut created, mut exit, mut kernel, mut user) = (
                    FileTime::default(),
                    FileTime::default(),
                    FileTime::default(),
                    FileTime::default(),
                );
                if unsafe {
                    GetProcessTimes(handle, &mut created, &mut exit, &mut kernel, &mut user)
                } == 0
                {
                    unsafe {
                        CloseHandle(handle);
                    };
                    return None;
                }
                Some(Self {
                    handle,
                    created: ((created.high as u64) << 32) | created.low as u64,
                })
            }
            pub(crate) fn terminate(&self) {
                unsafe {
                    TerminateProcess(self.handle, 1);
                }
            }
        }
        impl Drop for OwnedHandle {
            fn drop(&mut self) {
                unsafe {
                    CloseHandle(self.handle);
                }
            }
        }
    }
    #[cfg(target_os = "windows")]
    pub(crate) use windows::OwnedHandle;
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unresponsive_close_can_be_recovered_without_renderer() {
        let mut gate = CloseGate::default();
        let (id, timer) = gate.request().unwrap();
        assert!(timer);
        assert_eq!(gate.request(), Some((id, false)));
        assert!(gate.recover(id));
        assert!(gate.request().is_none());
        assert!(!gate.respond(id));
        assert!(gate.close());
        assert!(!gate.close());
    }
    #[test]
    fn healthy_defer_and_stale_responses_do_not_close_another_request() {
        let mut gate = CloseGate::default();
        let (id, _) = gate.request().unwrap();
        assert!(gate.respond(id));
        assert!(!gate.recover(id));
        let (next, _) = gate.request().unwrap();
        assert!(next > id);
        assert!(!gate.respond(id));
        assert!(gate.recover(next));
        gate.keep_open();
        assert!(gate.request().unwrap().0 > next);
    }
    #[test]
    fn shutdown_is_idempotent_and_invalidates_pending_timeout() {
        let mut gate = CloseGate::default();
        let (id, _) = gate.request().unwrap();
        assert!(gate.close());
        assert!(!gate.recover(id));
        assert!(gate.request().is_none());
    }
    #[test]
    fn stale_parent_pid_edges_are_rejected() {
        let parents = HashMap::from([(2, 1), (3, 2), (4, 1)]);
        let starts = HashMap::from([(1, 100), (2, 90), (3, 110), (4, 120)]);
        let edges = native_process::identity_edges(&parents, &starts);
        assert_eq!(descendants(1, &edges), vec![4]);
    }
    #[cfg(target_os = "windows")]
    #[test]
    fn verified_process_handle_terminates_only_its_owned_fixture() {
        use std::os::windows::process::CommandExt;
        let mut child = std::process::Command::new("powershell")
            .args(["-NoProfile", "-Command", "Start-Sleep -Seconds 30"])
            .creation_flags(super::super::CREATE_NO_WINDOW)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .unwrap();
        let handle = native_process::OwnedHandle::open(child.id(), true).unwrap();
        assert!(handle.created > 0);
        handle.terminate();
        let deadline = std::time::Instant::now() + Duration::from_secs(3);
        while child.try_wait().unwrap().is_none() && std::time::Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        let stopped = child.try_wait().unwrap().is_some();
        if !stopped {
            let _ = child.kill();
            let _ = child.wait();
        }
        assert!(stopped);
    }
    #[test]
    fn cleanup_is_scoped_to_descendants_and_handles_cycles() {
        let graph = HashMap::from([(2, 1), (3, 2), (4, 99), (5, 3), (1, 5)]);
        let found = descendants(1, &graph);
        assert_eq!(found, vec![5, 3, 2]);
        assert!(!found.contains(&4));
        assert!(!found.contains(&1));
    }
}

// Update handoff has its own validated helper; suppress the ordinary force-close path.
pub(crate) fn mark_update_exit(app: &tauri::AppHandle) {
    app.state::<CloseRecoveryState>()
        .0
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .close();
    app.state::<super::desktop_lifecycle::Lifecycle>()
        .admit_update_exit();
}
