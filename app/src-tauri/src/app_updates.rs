// SPDX-License-Identifier: Apache-2.0
//! Fixed update-cache/process boundary. Release policy remains in Python.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};
use tauri::Manager;

const MARKER: &str = "SPIKE-owned-update-cache-v1\n";
#[derive(Default)]
pub(crate) struct UpdateState(Mutex<UpdateData>);
#[derive(Default)]
struct UpdateData {
    snapshot: Value,
    cancel: Option<Arc<AtomicBool>>,
    busy: bool,
    workers: usize,
}

pub(crate) struct WorkAdmission(tauri::AppHandle);
impl Drop for WorkAdmission {
    fn drop(&mut self) {
        let state = self.0.state::<UpdateState>();
        if let Ok(mut data) = state.0.lock() {
            data.workers = data.workers.saturating_sub(1);
        };
    }
}
fn renderer_worker_allowed(method: &str) -> bool {
    !method.starts_with("app_update_")
}
pub(crate) fn admit_work(app: &tauri::AppHandle, method: &str) -> Result<WorkAdmission, String> {
    if !renderer_worker_allowed(method) {
        return Err("Use the dedicated native update commands".into());
    }
    let state = app.state::<UpdateState>();
    let mut data = state.0.lock().map_err(|e| e.to_string())?;
    if data.snapshot["status"] == "installing" {
        return Err("SPIKE is preparing to install its update".into());
    }
    data.workers += 1;
    Ok(WorkAdmission(app.clone()))
}
fn previous_outcome() -> Result<Option<Value>, String> {
    let path = cache()?.join("outcome.json");
    no_links(&path)?;
    if !path.exists() {
        return Ok(None);
    }
    if fs::metadata(&path).map_err(|e| e.to_string())?.len() > 8192 {
        return Err("Invalid update outcome record".into());
    }
    let value: Value = serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    if value["status"] != "failed" || !value["message"].is_string() {
        return Err("Invalid update outcome".into());
    }
    Ok(Some(value))
}
fn no_links(path: &Path) -> Result<(), String> {
    for item in path.ancestors() {
        match fs::symlink_metadata(item) {
            Ok(meta) => {
                #[cfg(target_os = "windows")]
                {
                    use std::os::windows::fs::MetadataExt;
                    if meta.file_attributes() & 0x400 != 0 {
                        return Err("Update cache contains a reparse point".into());
                    }
                }
                if meta.file_type().is_symlink() {
                    return Err("Update cache contains a symbolic link".into());
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.to_string()),
        }
    }
    Ok(())
}
fn cache() -> Result<PathBuf, String> {
    let base = PathBuf::from(
        std::env::var_os("LOCALAPPDATA").ok_or("Local application data unavailable")?,
    );
    if !base.is_absolute() {
        return Err("Invalid local application data location".into());
    }
    let root = base.join("SPIKE").join("updates").join("v1");
    no_links(&root)?;
    if !root.exists() {
        fs::create_dir_all(&root).map_err(|e| e.to_string())?;
        fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(root.join("owner.txt"))
            .and_then(|mut f| f.write_all(MARKER.as_bytes()))
            .map_err(|e| e.to_string())?;
    }
    let marker = root.join("owner.txt");
    no_links(&marker)?;
    if fs::metadata(&marker).map_err(|e| e.to_string())?.len() != MARKER.len() as u64
        || fs::read_to_string(marker).map_err(|e| e.to_string())? != MARKER
    {
        return Err("Unrecognized update cache".into());
    }
    Ok(root)
}
fn remove_owned(root: &Path, name: &str) -> Result<(), String> {
    if !matches!(
        name,
        "setup.exe" | "setup.partial" | "update-helper.exe" | "outcome.json"
    ) {
        return Err("Unowned update artifact".into());
    }
    let path = root.join(name);
    no_links(&path)?;
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
fn cache_lease() -> Result<fs::File, String> {
    let path = cache()?.join("update.lock");
    no_links(&path)?;
    let mut options = fs::OpenOptions::new();
    options.read(true).write(true).create(true);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(0);
    }
    options
        .open(path)
        .map_err(|_| "Another SPIKE instance owns the update cache".into())
}
fn clean() -> Result<(), String> {
    let _lease = cache_lease()?;
    clean_owned()
}
fn clean_owned() -> Result<(), String> {
    let root = cache()?;
    // Remove the helper first: Windows refuses this while an installer helper is live.
    for name in [
        "update-helper.exe",
        "setup.partial",
        "setup.exe",
        "outcome.json",
    ] {
        remove_owned(&root, name)?;
    }
    Ok(())
}
fn public(mut value: Value) -> Value {
    if let Some(o) = value.as_object_mut() {
        o.remove("download_url");
        o.remove("sha256");
    }
    value
}
fn main_only(window: &tauri::Window) -> Result<(), String> {
    if window.label() == "main" {
        Ok(())
    } else {
        Err("Updates are controlled by the main workspace".into())
    }
}
fn initial(app: &tauri::AppHandle) -> Value {
    json!({"contract":"spike/app-update/v1","status":"idle","current_version":app.package_info().version.to_string(),"received_bytes":0,"total_bytes":0})
}
#[tauri::command]
pub(crate) fn app_update_status(
    window: tauri::Window,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    main_only(&window)?;
    let state = app.state::<UpdateState>();
    let mut data = state.0.lock().map_err(|e| e.to_string())?;
    if data.snapshot.is_null() {
        data.snapshot = initial(&app);
        if cfg!(target_os = "windows") {
            if let Ok(Some(outcome)) = previous_outcome() {
                data.snapshot["status"] = json!("failed");
                data.snapshot["message"] = outcome["message"].clone();
                data.snapshot["error"] = outcome["message"].clone();
            }
            if let Err(error) = clean() {
                data.snapshot["message"] = json!(format!("Update cache cleanup pending: {error}"));
            }
        }
    }
    Ok(public(data.snapshot.clone()))
}
pub(crate) fn progress(app: &tauri::AppHandle, method: &str, frame: &Value) {
    if method != "app_update_download" {
        return;
    }
    let state = app.state::<UpdateState>();
    if let Ok(mut data) = state.0.lock() {
        if data.busy && data.snapshot["status"] == "downloading" {
            for key in ["received_bytes", "total_bytes"] {
                if frame[key].is_u64() {
                    data.snapshot[key] = frame[key].clone();
                }
            }
        }
    };
}
async fn operation(app: tauri::AppHandle, download: bool) -> Result<Value, String> {
    if !cfg!(target_os = "windows") {
        let mut value = initial(&app);
        value["status"] = json!("unsupported");
        value["message"] = json!("Automatic setup updates currently require Windows");
        app.state::<UpdateState>()
            .0
            .lock()
            .map_err(|e| e.to_string())?
            .snapshot = value.clone();
        return Ok(value);
    }
    let cancel = Arc::new(AtomicBool::new(false));
    let previous = {
        let state = app.state::<UpdateState>();
        let mut data = state.0.lock().map_err(|e| e.to_string())?;
        if data.busy {
            return Err("An update operation is already running".into());
        }
        if download && data.snapshot["status"] != "available" {
            return Err("Check for an available update first".into());
        }
        let previous = data.snapshot.clone();
        data.busy = true;
        data.cancel = Some(cancel.clone());
        if !download {
            data.snapshot = initial(&app);
        }
        data.snapshot["status"] = json!(if download { "downloading" } else { "checking" });
        previous
    };
    let task_app = app.clone();
    let task_cancel = cancel.clone();
    let result=tauri::async_runtime::spawn_blocking(move||{
        let _lease=cache_lease()?;
        if !download {clean_owned()?;}
        super::run_worker_process(task_app.clone(),json!({"id":"spike-app-update","method":if download{"app_update_download"}else{"app_update_check"},"params":{
            "current_version":task_app.package_info().version.to_string(),"platform":std::env::consts::OS,"machine":std::env::consts::ARCH,
            "latest_version":previous["latest_version"],"timeout_seconds":1800}}),Some(task_cancel))
    }).await.map_err(|e|e.to_string()).and_then(|r|r).and_then(|r|if r["ok"]==true{Ok(r["result"].clone())}else{Err(r["error"].as_str().unwrap_or("Update worker failed").to_string())});
    let state = app.state::<UpdateState>();
    let mut data = state.0.lock().map_err(|e| e.to_string())?;
    data.busy = false;
    data.cancel = None;
    match result {
        Ok(v) if !cancel.load(Ordering::SeqCst) => data.snapshot = v,
        _ => {
            let message = result.err().unwrap_or_else(|| "Update cancelled".into());
            data.snapshot["status"] = json!(if cancel.load(Ordering::SeqCst) {
                "cancelled"
            } else {
                "failed"
            });
            data.snapshot["message"] = json!(message);
            data.snapshot["error"] = data.snapshot["message"].clone();
            if let Err(e) = clean() {
                data.snapshot["message"] = json!(format!(
                    "{} Cache cleanup pending: {e}",
                    data.snapshot["message"].as_str().unwrap_or("Update failed")
                ));
            }
        }
    }
    Ok(public(data.snapshot.clone()))
}
#[tauri::command]
pub(crate) async fn app_update_check(
    window: tauri::Window,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    main_only(&window)?;
    operation(app, false).await
}
#[tauri::command]
pub(crate) async fn app_update_download(
    window: tauri::Window,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    main_only(&window)?;
    operation(app, true).await
}
#[tauri::command]
pub(crate) fn app_update_cancel(
    window: tauri::Window,
    app: tauri::AppHandle,
) -> Result<Value, String> {
    main_only(&window)?;
    let state = app.state::<UpdateState>();
    let data = state.0.lock().map_err(|e| e.to_string())?;
    if let Some(flag) = &data.cancel {
        flag.store(true, Ordering::SeqCst);
    }
    Ok(public(data.snapshot.clone()))
}

fn verify_setup(root: &Path, digest: &str, size: u64) -> Result<fs::File, String> {
    if digest.len() != 64
        || !digest.bytes().all(|c| c.is_ascii_hexdigit())
        || size == 0
        || size > 4 * 1024 * 1024 * 1024
    {
        return Err("Invalid installer integrity contract".into());
    }
    let path = root.join("setup.exe");
    no_links(&path)?;
    let mut options = fs::OpenOptions::new();
    options.read(true);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::fs::OpenOptionsExt;
        options.share_mode(1);
    }
    let mut file = options.open(path).map_err(|e| e.to_string())?;
    if !file.metadata().map_err(|e| e.to_string())?.is_file()
        || file.metadata().map_err(|e| e.to_string())?.len() != size
    {
        return Err("Installer size changed".into());
    }
    let mut hash = Sha256::new();
    let mut block = [0u8; 65536];
    loop {
        let count = file.read(&mut block).map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        hash.update(&block[..count]);
    }
    if hex::encode(hash.finalize()) != digest {
        return Err("Installer SHA-256 changed".into());
    }
    Ok(file)
}

#[tauri::command]
pub(crate) async fn app_update_install(
    window: tauri::Window,
    app: tauri::AppHandle,
    acknowledged: bool,
    unattended: bool,
) -> Result<Value, String> {
    main_only(&window)?;
    if !acknowledged {
        return Err("Save and close your work, then acknowledge installation".into());
    }
    if !cfg!(target_os = "windows") {
        return Err("Automatic installation currently requires Windows".into());
    }
    if app.webview_windows().len() != 1 {
        return Err("Close all detached tools and draft editors before installation".into());
    }
    let snapshot = {
        let state = app.state::<UpdateState>();
        let mut data = state.0.lock().map_err(|e| e.to_string())?;
        if data.busy || data.workers > 0 || data.snapshot["status"] != "ready" {
            return Err("A verified installer is required".into());
        }
        data.busy = true;
        data.snapshot["status"] = json!("installing");
        data.snapshot.clone()
    };
    let app2 = app.clone();
    let result =
        tauri::async_runtime::spawn_blocking(move || handoff(&app2, &snapshot, unattended))
            .await
            .map_err(|e| e.to_string())
            .and_then(|r| r);
    if let Err(error) = result {
        let state = app.state::<UpdateState>();
        let mut data = state.0.lock().map_err(|e| e.to_string())?;
        data.busy = false;
        data.snapshot["status"] = json!("ready");
        data.snapshot["message"] = json!(error.clone());
        return Err(error);
    }
    let value = app_update_status(window, app.clone())?;
    app.exit(0);
    Ok(value)
}
fn handoff(app: &tauri::AppHandle, snapshot: &Value, unattended: bool) -> Result<(), String> {
    if unattended && snapshot["unattended_supported"] != true {
        return Err("This installer does not support background installation".into());
    }
    let active = app.state::<super::WorkerExecutionState>();
    let guard = active.0.lock().map_err(|e| e.to_string())?;
    if guard.is_some() {
        return Err("Wait for active workers before installing".into());
    }
    let resident = app.state::<super::ResidentWorkerState>();
    if resident
        .0
        .try_lock()
        .map_err(|_| "The resident circuit worker is busy")?
        .is_some()
    {
        return Err("Close all circuit sessions before installing. If a session cannot close, save your work, restart SPIKE, then check and download again.".into());
    }
    let _lease = cache_lease()?;
    let root = cache()?;
    let digest = snapshot["sha256"]
        .as_str()
        .ok_or("Installer digest unavailable")?;
    let size = snapshot["size"]
        .as_u64()
        .ok_or("Installer size unavailable")?;
    let locked = verify_setup(&root, digest, size)?;
    remove_owned(&root, "update-helper.exe")?;
    remove_owned(&root, "outcome.json")?;
    let helper = root.join("update-helper.exe");
    no_links(&helper)?;
    let mut out = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&helper)
        .map_err(|e| e.to_string())?;
    std::io::copy(
        &mut fs::File::open(std::env::current_exe().map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?,
        &mut out,
    )
    .map_err(|e| e.to_string())?;
    drop(out);
    let mut command = Command::new(&helper);
    command
        .args([
            "--spike-update-helper",
            digest,
            &size.to_string(),
            &std::process::id().to_string(),
            if unattended { "silent" } else { "interactive" },
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let stdout = child.stdout.take().ok_or("Update helper output missing")?;
    let (send, receive) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        use std::io::BufRead;
        let mut line = String::new();
        let result = std::io::BufReader::new(stdout)
            .read_line(&mut line)
            .map(|_| line);
        let _ = send.send(result);
    });
    let ready = match receive.recv_timeout(std::time::Duration::from_secs(30)) {
        Ok(Ok(line)) => line,
        _ => {
            let _ = child.kill();
            let _ = child.wait();
            let _ = remove_owned(&root, "update-helper.exe");
            return Err("Update helper timed out before verification".into());
        }
    };
    if ready.trim() != "SPIKE_UPDATE_READY" {
        let _ = child.kill();
        let _ = child.wait();
        let _ = remove_owned(&root, "update-helper.exe");
        return Err("Update helper could not verify setup".into());
    }
    // Recheck after helper verification: a pending tool window may have opened
    // since the initial guard. Never authorize setup when a new draft can exist.
    if app.webview_windows().len() != 1 {
        let _ = child.kill();
        let _ = child.wait();
        let _ = remove_owned(&root, "update-helper.exe");
        return Err("A tool window opened during update preparation. Close it after saving its work, then retry installation.".into());
    }
    // Allow launch only after all handoff preparation succeeded. EOF alone never authorizes it.
    child
        .stdin
        .take()
        .ok_or("Update helper input missing")?
        .write_all(b"INSTALL\n")
        .map_err(|e| e.to_string())?;
    drop(locked);
    super::close_recovery::mark_update_exit(app);
    Ok(())
}

/// Copied executable helper runs without loading Tauri or the installed worker.
pub(crate) fn helper_entry() -> bool {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) != Some("--spike-update-helper") {
        return false;
    }
    let result = helper(&args);
    if let Err(error) = result {
        if let Ok(root) = cache() {
            let p = root.join("outcome.json");
            if no_links(&p).is_ok() {
                let _ = fs::OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(p)
                    .and_then(|mut f| {
                        f.write_all(
                            json!({"status":"failed","message":error})
                                .to_string()
                                .as_bytes(),
                        )
                    });
            }
        }
    }
    true
}
#[cfg(target_os = "windows")]
fn helper(args: &[String]) -> Result<(), String> {
    use std::ffi::c_void;
    #[link(name = "kernel32")]
    extern "system" {
        fn OpenProcess(access: u32, inherit: i32, pid: u32) -> *mut c_void;
        fn WaitForSingleObject(handle: *mut c_void, millis: u32) -> u32;
        fn CloseHandle(handle: *mut c_void) -> i32;
    }
    if args.len() != 6 || !matches!(args[5].as_str(), "silent" | "interactive") {
        return Err("Invalid update helper invocation".into());
    }
    let root = cache()?;
    if std::env::current_exe().map_err(|e| e.to_string())? != root.join("update-helper.exe") {
        return Err("Update helper is outside its owned cache".into());
    }
    let size = args[3].parse::<u64>().map_err(|e| e.to_string())?;
    let pid = args[4].parse::<u32>().map_err(|e| e.to_string())?;
    let lock = verify_setup(&root, &args[2], size)?;
    let parent = unsafe { OpenProcess(0x00100000, 0, pid) };
    if parent.is_null() {
        return Err("Cannot pin the updating application".into());
    }
    println!("SPIKE_UPDATE_READY");
    std::io::stdout().flush().map_err(|e| e.to_string())?;
    let mut approval = String::new();
    std::io::stdin()
        .take(32)
        .read_to_string(&mut approval)
        .map_err(|e| e.to_string())?;
    if approval != "INSTALL\n" {
        unsafe { CloseHandle(parent) };
        return Err("Update handoff was not authorized".into());
    }
    let exited = unsafe { WaitForSingleObject(parent, 30000) };
    unsafe { CloseHandle(parent) };
    if exited != 0 {
        return Err("SPIKE did not exit; installation cancelled".into());
    }
    no_links(&root.join("setup.exe"))?;
    let mut command = Command::new(root.join("setup.exe"));
    command.arg("/UPDATE");
    if args[5] == "silent" {
        command.arg("/S");
    }
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    drop(lock);
    let status = child.wait().map_err(|e| e.to_string())?;
    remove_owned(&root, "setup.exe")?;
    if !status.success() {
        return Err(format!(
            "Setup exited with {status}; installation was not confirmed"
        ));
    }
    Ok(())
}
#[cfg(not(target_os = "windows"))]
fn helper(_args: &[String]) -> Result<(), String> {
    Err("Update helper requires Windows".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn public_result_never_exposes_execution_authority() {
        let v =
            public(json!({"sha256":"abc","download_url":"https://example.org","status":"ready"}));
        assert!(v.get("sha256").is_none());
        assert!(v.get("download_url").is_none());
        assert_eq!(v["status"], "ready");
    }
    #[test]
    fn delete_boundary_rejects_other_names() {
        assert!(remove_owned(Path::new("."), "project.spike").is_err());
        assert!(remove_owned(Path::new("."), "../setup.exe").is_err());
    }
    #[test]
    fn malformed_integrity_never_opens_a_file() {
        assert!(verify_setup(Path::new("."), "bad", 100).is_err());
        assert!(verify_setup(Path::new("."), &"0".repeat(64), 0).is_err());
    }
    #[test]
    fn renderer_routes_cannot_request_update_services() {
        assert!(!renderer_worker_allowed("app_update_download"));
        assert!(!renderer_worker_allowed("app_update_check"));
        assert!(renderer_worker_allowed("health"));
    }
    #[test]
    fn setup_tampering_and_foreign_cleanup_are_rejected() {
        let root = std::env::temp_dir().join(format!(
            "spike-update-test-{}-{}",
            std::process::id(),
            super::super::unix_time_ms()
        ));
        fs::create_dir(&root).unwrap();
        let setup = root.join("setup.exe");
        let project = root.join("user-project.spike");
        fs::write(&setup, b"fixture only").unwrap();
        fs::write(&project, b"preserve me").unwrap();
        let digest = hex::encode(Sha256::digest(b"fixture only"));
        let file = verify_setup(&root, &digest, 12).unwrap();
        #[cfg(target_os = "windows")]
        {
            assert!(fs::write(&setup, b"modified!!!!").is_err());
            assert!(fs::remove_file(&setup).is_err());
        }
        drop(file);
        fs::write(&setup, b"modified!!!!").unwrap();
        assert!(verify_setup(&root, &digest, 12).is_err());
        assert!(remove_owned(&root, "user-project.spike").is_err());
        assert_eq!(fs::read(&project).unwrap(), b"preserve me");
        remove_owned(&root, "setup.exe").unwrap();
        fs::remove_file(project).unwrap();
        fs::remove_dir(root).unwrap();
    }
}
