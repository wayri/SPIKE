// SPDX-License-Identifier: Apache-2.0
//! Track admitted resident sessions solely to release an unused worker process.

use serde_json::Value;
use std::collections::HashSet;

pub(crate) struct ResidentSessions {
    live: HashSet<String>,
    complete: bool,
}

impl Default for ResidentSessions {
    fn default() -> Self {
        Self {
            live: HashSet::new(),
            complete: true,
        }
    }
}

impl ResidentSessions {
    /// Return true only when a successful close proves no admitted session
    /// remains. Failed or malformed replies never authorize process retirement.
    pub(crate) fn observe(&mut self, request: &Value, response: &Value) -> bool {
        if response.get("ok").and_then(Value::as_bool) != Some(true) {
            return false;
        }
        let result = &response["result"];
        match request["method"].as_str() {
            Some("spikes_session_create") => {
                if let Some(id) = result["session_id"].as_str().filter(|id| !id.is_empty()) {
                    self.live.insert(id.to_string());
                } else {
                    // A successful but unidentifiable session must not be lost
                    // when the last identifiable session is closed later.
                    self.complete = false;
                }
                false
            }
            Some("spikes_session_close") if result["status"] == "closed" => {
                let Some(id) = request["params"]["session_id"].as_str() else {
                    return false;
                };
                if result["session_id"].as_str() != Some(id) {
                    return false;
                }
                self.live.remove(id) && self.live.is_empty() && self.complete
            }
            _ => false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn failed_or_unidentifiable_responses_never_retire_other_sessions() {
        let mut sessions = ResidentSessions::default();
        let create = json!({"method": "spikes_session_create"});
        let close = json!({"method": "spikes_session_close", "params": {"session_id": "a"}});
        assert!(!sessions.observe(&create, &json!({"ok": true, "result": {"session_id": "a"}})));
        assert!(!sessions.observe(&close, &json!({"ok": false})));
        assert!(!sessions.observe(
            &close,
            &json!({"ok": true, "result": {"status": "closed", "session_id": "b"}})
        ));
        assert!(!sessions.observe(&create, &json!({"ok": true, "result": {}})));
        assert!(!sessions.observe(
            &close,
            &json!({"ok": true, "result": {"status": "closed", "session_id": "a"}})
        ));
    }
    #[test]
    fn final_resident_close_retires_worker_without_losing_other_sessions() {
        use std::process::{Command, Stdio};
        use std::sync::{mpsc, Arc, Mutex};
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
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let stdin = child.stdin.take();
        let original_pid = child.id();
        let (response_sender, responses) = mpsc::channel();
        let (_stderr_sender, stderr) = mpsc::channel();
        let resident = Arc::new(Mutex::new(Some(super::super::ResidentWorker {
            child,
            stdin,
            responses,
            stderr,
            sessions: ResidentSessions::default(),
        })));
        for (id, method, session_id, expected_running) in [
            ("c1", "spikes_session_create", "a", true),
            ("c2", "spikes_session_create", "b", true),
            ("x1", "spikes_session_close", "a", true),
            ("x2", "spikes_session_close", "b", false),
        ] {
            let response = json!({"id": id, "ok": true, "result": {
                "status": if method.ends_with("close") {"closed"} else {"ready"},
                "session_id": session_id,
            }});
            response_sender
                .send(Ok(serde_json::to_vec(&response).unwrap()))
                .unwrap();
            assert_eq!(
                super::super::run_resident_worker_request(
                    std::path::Path::new("."),
                    &resident,
                    json!({"id": id, "method": method, "params": {"session_id": session_id}}),
                    None,
                    &super::super::desktop_lifecycle::Lifecycle::default(),
                )
                .unwrap(),
                response
            );
            let mut state = resident.lock().unwrap();
            assert_eq!(state.is_some(), expected_running);
            if let Some(worker) = state.as_mut() {
                assert_eq!(worker.child.id(), original_pid);
                assert!(worker.child.try_wait().unwrap().is_none());
            }
        }
    }
}
