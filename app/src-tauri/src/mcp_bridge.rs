// SPDX-License-Identifier: Apache-2.0
//! Opt-in, authenticated local IPC to the main UI; no domain or solver dispatch.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};

const MAX_REQUEST: usize = 1024 * 1024;
const MAX_RESPONSE: usize = 8 * 1024 * 1024;
const FRAME_TIMEOUT: Duration = Duration::from_secs(5);
const COMMAND_TIMEOUT: Duration = Duration::from_secs(30);
const COMMANDS: &[&str] = &[
    "status",
    "select_workspace",
    "set_view_mode",
    "list_studies",
    "create_study",
    "add_study_case",
    "activate_study_case",
    "open_run_controls",
];

type Pending = Arc<Mutex<Option<(String, mpsc::Sender<Value>)>>>;

#[derive(Default)]
pub struct BridgeState {
    running: Mutex<Option<Running>>,
}

struct Running {
    stop: Arc<AtomicBool>,
    pending: Pending,
    path: PathBuf,
    port: u16,
}

impl Drop for Running {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Ok(mut pending) = self.pending.lock() {
            *pending = None;
        }
        let _ = fs::remove_file(&self.path);
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BridgeStatus {
    enabled: bool,
    rendezvous_path: Option<String>,
    port: Option<u16>,
}

impl BridgeState {
    pub fn stop(&self) {
        if let Ok(mut running) = self.running.lock() {
            *running = None;
        }
    }
}

fn status(running: &Option<Running>) -> BridgeStatus {
    BridgeStatus {
        enabled: running.is_some(),
        rendezvous_path: running
            .as_ref()
            .map(|r| r.path.to_string_lossy().into_owned()),
        port: running.as_ref().map(|r| r.port),
    }
}

fn trusted_origin(url: &tauri::Url) -> bool {
    let packaged = (url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (matches!(url.scheme(), "http" | "https")
            && url.host_str() == Some("tauri.localhost")
            && url.port().is_none());
    let development = cfg!(debug_assertions)
        && url.scheme() == "http"
        && url.host_str() == Some("localhost")
        && url.port() == Some(1420);
    (packaged || development) && url.username().is_empty() && url.password().is_none()
}

fn require_main(window: &tauri::WebviewWindow) -> Result<(), String> {
    if window.label() != "main" || !trusted_origin(&window.url().map_err(|e| e.to_string())?) {
        return Err("MCP bridge commands require the trusted main application window".into());
    }
    Ok(())
}

#[tauri::command]
pub fn mcp_bridge_status(
    window: tauri::WebviewWindow,
    state: tauri::State<BridgeState>,
) -> Result<BridgeStatus, String> {
    require_main(&window)?;
    let running = state
        .running
        .lock()
        .map_err(|_| "Bridge state unavailable")?;
    Ok(status(&running))
}

#[tauri::command]
pub fn mcp_bridge_stop(
    window: tauri::WebviewWindow,
    state: tauri::State<BridgeState>,
) -> Result<BridgeStatus, String> {
    require_main(&window)?;
    state.stop();
    Ok(status(&None))
}

#[tauri::command]
pub fn mcp_bridge_start(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    state: tauri::State<BridgeState>,
) -> Result<BridgeStatus, String> {
    require_main(&window)?;
    let mut running = state
        .running
        .lock()
        .map_err(|_| "Bridge state unavailable")?;
    if running.is_some() {
        return Ok(status(&running));
    }
    let token = random_id()?;
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|e| e.to_string())?;
    listener.set_nonblocking(true).map_err(|e| e.to_string())?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    let directory = app
        .path()
        .app_local_data_dir()
        .map_err(|e| e.to_string())?
        .join("mcp");
    private_directory(&directory)?;
    let path = directory.join(format!("bridge-{}.json", std::process::id()));
    write_rendezvous(
        &path,
        &json!({"version": 1, "host": "127.0.0.1", "port": port,
        "token": token, "pid": std::process::id()}),
    )?;
    let active = Running {
        stop: Arc::new(AtomicBool::new(false)),
        pending: Arc::new(Mutex::new(None)),
        path,
        port,
    };
    let stop = active.stop.clone();
    let pending = active.pending.clone();
    // A single consumer serializes UI changes and bounds pending memory/thread usage.
    thread::Builder::new()
        .name("spike-mcp-bridge".into())
        .spawn(move || {
            while !stop.load(Ordering::Acquire) {
                match listener.accept() {
                    Ok((mut stream, peer)) if peer.ip().is_loopback() => {
                        let response = exchange(&mut stream, &token, &stop, &pending, |request| {
                            let main = app
                                .get_webview_window("main")
                                .ok_or("Main window unavailable")?;
                            require_main(&main)?;
                            main.emit("spike:mcp-request", request)
                                .map_err(|e| e.to_string())
                        });
                        let _ = write_network_response(&mut stream, &response);
                    }
                    Ok(_) => {}
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(40))
                    }
                    Err(_) => break,
                }
            }
        })
        .map_err(|e| e.to_string())?;
    *running = Some(active);
    Ok(status(&running))
}

#[tauri::command]
pub fn mcp_bridge_respond(
    window: tauri::WebviewWindow,
    state: tauri::State<BridgeState>,
    request_id: String,
    result: Option<Value>,
    error: Option<String>,
) -> Result<(), String> {
    require_main(&window)?;
    let response = match (result, error) {
        (Some(result), None) => json!({"ok": true, "result": result}),
        (None, Some(error)) => json!({"ok": false, "error": error}),
        _ => return Err("Supply exactly one of result or error".into()),
    };
    if serde_json::to_vec(&response)
        .map_err(|e| e.to_string())?
        .len()
        > MAX_RESPONSE - 512
    {
        return Err("MCP response exceeds the 8 MiB limit".into());
    }
    let running = state
        .running
        .lock()
        .map_err(|_| "Bridge state unavailable")?;
    let active = running.as_ref().ok_or("MCP bridge is disabled")?;
    let mut pending = active
        .pending
        .lock()
        .map_err(|_| "Bridge request unavailable")?;
    if pending.as_ref().map(|p| p.0.as_str()) != Some(request_id.as_str()) {
        return Err("Unknown or expired MCP request".into());
    }
    pending
        .take()
        .unwrap()
        .1
        .send(response)
        .map_err(|_| "MCP client disconnected".into())
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Request {
    token: String,
    request_id: String,
    command: String,
    args: serde_json::Map<String, Value>,
}

fn random_id() -> Result<String, String> {
    let mut bytes = [0_u8; 32];
    getrandom::fill(&mut bytes).map_err(|e| format!("Secure randomness unavailable: {e}"))?;
    Ok(hex::encode(bytes))
}

fn parse_request(bytes: &[u8], token: &str) -> Result<Request, String> {
    let request: Request = serde_json::from_slice(bytes).map_err(|_| "Malformed bridge request")?;
    // Fixed-size compare avoids exposing a matching token prefix.
    let authenticated = request.token.len() == token.len()
        && request
            .token
            .as_bytes()
            .iter()
            .zip(token.as_bytes())
            .fold(0_u8, |difference, (a, b)| difference | (a ^ b))
            == 0;
    if !authenticated {
        return Err("Unauthorized bridge request".into());
    }
    if request.request_id.is_empty() || request.request_id.len() > 128 {
        return Err("requestId must contain 1 to 128 bytes".into());
    }
    if !COMMANDS.contains(&request.command.as_str()) {
        return Err("Unsupported bridge command".into());
    }
    Ok(request)
}

fn read_frame(stream: &mut TcpStream, stop: &AtomicBool) -> Result<Vec<u8>, String> {
    let deadline = Instant::now() + FRAME_TIMEOUT;
    let mut bytes = Vec::new();
    let mut chunk = [0_u8; 8192];
    while !stop.load(Ordering::Acquire) && Instant::now() < deadline {
        stream
            .set_read_timeout(Some(Duration::from_millis(100)))
            .map_err(|e| e.to_string())?;
        match stream.read(&mut chunk) {
            Ok(0) => return Err("Bridge request requires a newline terminator".into()),
            Ok(count) => {
                if bytes.len() + count > MAX_REQUEST {
                    return Err("Bridge request exceeds 1 MiB".into());
                }
                if let Some(end) = chunk[..count].iter().position(|byte| *byte == b'\n') {
                    if end + 1 != count {
                        return Err("Only one JSON request per connection is allowed".into());
                    }
                    bytes.extend_from_slice(&chunk[..end]);
                    return Ok(bytes);
                }
                bytes.extend_from_slice(&chunk[..count]);
            }
            Err(e)
                if matches!(
                    e.kind(),
                    std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock
                ) => {}
            Err(e) => return Err(e.to_string()),
        }
    }
    Err("Bridge request interrupted or timed out".into())
}

fn exchange(
    stream: &mut TcpStream,
    token: &str,
    stop: &AtomicBool,
    pending: &Pending,
    emit: impl FnOnce(Value) -> Result<(), String>,
) -> Value {
    let request = match read_frame(stream, stop).and_then(|bytes| parse_request(&bytes, token)) {
        Ok(request) => request,
        Err(error) => return json!({"requestId": null, "ok": false, "error": error}),
    };
    let failure =
        |error: &str| json!({"requestId": request.request_id, "ok": false, "error": error});
    if stop.load(Ordering::Acquire) {
        return failure("MCP bridge is disabled");
    }
    // GUI correlation IDs are host-generated; a late response cannot fulfill a new request.
    let internal_id = match random_id() {
        Ok(id) => id,
        Err(error) => return failure(&error),
    };
    let (sender, receiver) = mpsc::channel();
    if let Ok(mut active) = pending.lock() {
        *active = Some((internal_id.clone(), sender));
    } else {
        return failure("Bridge request unavailable");
    }
    let dispatched =
        emit(json!({"requestId": internal_id, "command": request.command, "args": request.args}));
    let deadline = Instant::now() + COMMAND_TIMEOUT;
    let response = match dispatched {
        Err(error) => failure(&error),
        Ok(()) => loop {
            if stop.load(Ordering::Acquire) {
                break failure("MCP bridge stopped");
            }
            if Instant::now() >= deadline {
                break failure("UI command timed out; inspect application state before retrying");
            }
            match receiver.recv_timeout(Duration::from_millis(100)) {
                Ok(mut result) => {
                    result["requestId"] = json!(request.request_id);
                    break result;
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {}
                Err(_) => break failure("UI response channel closed"),
            }
        },
    };
    if let Ok(mut active) = pending.lock() {
        *active = None;
    }
    response
}

fn write_response(writer: &mut impl Write, response: &Value) -> Result<(), String> {
    let mut bytes = serde_json::to_vec(response).map_err(|e| e.to_string())?;
    if bytes.len() > MAX_RESPONSE {
        return Err("MCP response exceeds 8 MiB".into());
    }
    bytes.push(b'\n');
    writer.write_all(&bytes).map_err(|e| e.to_string())
}

fn write_network_response(stream: &mut TcpStream, response: &Value) -> Result<(), String> {
    let mut bytes = Vec::new();
    write_response(&mut bytes, response)?;
    let deadline = Instant::now() + Duration::from_secs(2);
    let mut remaining = bytes.as_slice();
    while !remaining.is_empty() {
        let timeout = deadline
            .checked_duration_since(Instant::now())
            .ok_or("Bridge response timed out")?;
        stream
            .set_write_timeout(Some(timeout))
            .map_err(|e| e.to_string())?;
        let written = stream.write(remaining).map_err(|e| e.to_string())?;
        if written == 0 {
            return Err("Bridge connection closed".into());
        }
        remaining = &remaining[written..];
    }
    Ok(())
}

fn private_directory(directory: &Path) -> Result<(), String> {
    fs::create_dir_all(directory).map_err(|e| e.to_string())?;
    if fs::symlink_metadata(directory)
        .map_err(|e| e.to_string())?
        .file_type()
        .is_symlink()
    {
        return Err("MCP directory cannot be a symbolic link".into());
    }
    restrict_permissions(directory, true)
}

fn write_rendezvous(path: &Path, value: &Value) -> Result<(), String> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(path)
        .map_err(|e| format!("Cannot create MCP rendezvous file: {e}"))?;
    let result = restrict_permissions(path, false).and_then(|()| {
        file.write_all(
            serde_json::to_string(value)
                .map_err(|e| e.to_string())?
                .as_bytes(),
        )
        .map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())
    });
    if result.is_err() {
        drop(file);
        let _ = fs::remove_file(path);
    }
    result
}

#[cfg(unix)]
fn restrict_permissions(path: &Path, directory: bool) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(
        path,
        fs::Permissions::from_mode(if directory { 0o700 } else { 0o600 }),
    )
    .map_err(|e| e.to_string())
}

#[cfg(windows)]
fn restrict_permissions(path: &Path, directory: bool) -> Result<(), String> {
    use std::ffi::c_void;
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "advapi32")]
    extern "system" {
        fn ConvertStringSecurityDescriptorToSecurityDescriptorW(
            text: *const u16,
            revision: u32,
            descriptor: *mut *mut c_void,
            size: *mut u32,
        ) -> i32;
        fn SetFileSecurityW(path: *const u16, information: u32, descriptor: *mut c_void) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn LocalFree(memory: *mut c_void) -> *mut c_void;
    }
    // Protected DACL grants access only to the object's owner. Directory ACEs
    // also inherit to new rendezvous files; secrets are written after protection.
    let sddl = if directory {
        "D:P(A;OICI;FA;;;OW)"
    } else {
        "D:P(A;;FA;;;OW)"
    };
    let descriptor_text: Vec<u16> = sddl.encode_utf16().chain(Some(0)).collect();
    let path_text: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut descriptor = std::ptr::null_mut();
    unsafe {
        if ConvertStringSecurityDescriptorToSecurityDescriptorW(
            descriptor_text.as_ptr(),
            1,
            &mut descriptor,
            std::ptr::null_mut(),
        ) == 0
        {
            return Err(format!(
                "Cannot construct private MCP permissions: {}",
                std::io::Error::last_os_error()
            ));
        }
        let success = SetFileSecurityW(path_text.as_ptr(), 0x80000004, descriptor);
        let error = std::io::Error::last_os_error();
        LocalFree(descriptor);
        if success == 0 {
            return Err(format!("Cannot restrict MCP permissions: {error}"));
        }
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn restrict_permissions(_: &Path, _: bool) -> Result<(), String> {
    Err("Private MCP rendezvous files are unsupported on this platform".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn authentication_and_allowlist_fail_closed() {
        let valid = json!({"token":"secret", "requestId":"a", "command":"status", "args":{}});
        assert!(parse_request(&serde_json::to_vec(&valid).unwrap(), "secret").is_ok());
        for (field, value) in [
            ("token", json!("wrong")),
            ("command", json!("run_worker")),
            ("requestId", json!("")),
            ("args", json!([])),
            ("origin", json!("https://evil.example")),
        ] {
            let mut request = valid.clone();
            request[field] = value;
            assert!(parse_request(&serde_json::to_vec(&request).unwrap(), "secret").is_err());
        }
        assert!(parse_request(b"POST / HTTP/1.1", "secret").is_err());
    }

    #[test]
    fn rejects_untrusted_origins() {
        assert!(trusted_origin(
            &tauri::Url::parse("http://tauri.localhost/").unwrap()
        ));
        for url in [
            "https://evil.example",
            "http://tauri.localhost.evil.example",
            "http://localhost:9999",
            "http://user@tauri.localhost",
            "http://tauri.localhost:8765",
        ] {
            assert!(!trusted_origin(&tauri::Url::parse(url).unwrap()));
        }
    }

    #[test]
    fn private_rendezvous_and_stop_cleanup() {
        let directory =
            std::env::temp_dir().join(format!("spike-mcp-test-{}", random_id().unwrap()));
        private_directory(&directory).unwrap();
        let path = directory.join("bridge.json");
        write_rendezvous(&path, &json!({"token":"secret"})).unwrap();
        assert!(write_rendezvous(&path, &json!({})).is_err());
        assert_eq!(fs::read_to_string(&path).unwrap(), "{\"token\":\"secret\"}");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
        let running = Running {
            stop: Arc::new(AtomicBool::new(false)),
            pending: Arc::new(Mutex::new(None)),
            path: path.clone(),
            port: 1,
        };
        let stop = running.stop.clone();
        let state = BridgeState {
            running: Mutex::new(Some(running)),
        };
        assert!(status(&state.running.lock().unwrap()).enabled);
        state.stop();
        assert!(!status(&state.running.lock().unwrap()).enabled);
        assert!(!path.exists());
        assert!(stop.load(Ordering::Acquire));
        fs::remove_dir(&directory).unwrap();
    }

    #[test]
    fn tcp_framing_and_response_correlation() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let mut client = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
        let (mut server, _) = listener.accept().unwrap();
        let pending: Pending = Arc::new(Mutex::new(None));
        client.write_all(b"{\"token\":\"secret\",\"requestId\":\"client-id\",\"command\":\"status\",\"args\":{}}\n").unwrap();
        let response = exchange(
            &mut server,
            "secret",
            &AtomicBool::new(false),
            &pending,
            |event| {
                assert_ne!(event["requestId"], "client-id");
                let (_, sender) = pending.lock().unwrap().take().unwrap();
                sender
                    .send(json!({"ok":true,"result":{"enabled":true}}))
                    .unwrap();
                Ok(())
            },
        );
        assert_eq!(response["requestId"], "client-id");
        assert_eq!(response["result"]["enabled"], true);
        let mut output = Vec::new();
        write_response(&mut output, &response).unwrap();
        assert_eq!(output.last(), Some(&b'\n'));
        assert!(pending.lock().unwrap().is_none());
    }

    #[test]
    fn rejects_oversize_unterminated_and_stopped_frames() {
        for bytes in [
            vec![b'x'; MAX_REQUEST + 1],
            b"{}".to_vec(),
            b"{}\n{}\n".to_vec(),
        ] {
            let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            let mut client = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
            let (mut server, _) = listener.accept().unwrap();
            let writer = thread::spawn(move || {
                let _ = client.write_all(&bytes);
                let _ = client.shutdown(std::net::Shutdown::Write);
            });
            assert!(read_frame(&mut server, &AtomicBool::new(false)).is_err());
            drop(server);
            writer.join().unwrap();
        }
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let _client = TcpStream::connect(listener.local_addr().unwrap()).unwrap();
        let (mut server, _) = listener.accept().unwrap();
        assert!(read_frame(&mut server, &AtomicBool::new(true)).is_err());
        assert!(
            write_response(&mut Vec::new(), &json!({"data":"x".repeat(MAX_RESPONSE)})).is_err()
        );
    }
}
