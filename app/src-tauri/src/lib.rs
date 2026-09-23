use serde::Serialize;
use std::collections::HashSet;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use sysinfo::{get_current_pid, Pid, ProcessRefreshKind, ProcessesToUpdate, System};
use tauri::Manager;

mod entitlement;
mod gpu_metrics;
mod extension_artifacts;
mod package_trust;
mod project_trust_binding;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct ResourceSampler {
    system: System,
    gpu: gpu_metrics::Sampler,
    last_sample: Option<Instant>,
}
struct ResourceState(Mutex<ResourceSampler>);
struct ApprovedFileState(Mutex<HashSet<PathBuf>>);
struct PendingOpenState(Mutex<Option<SelectedFile>>);
struct WorkerExecutionState(Arc<Mutex<Option<ActiveWorker>>>);
struct ResidentWorkerState(Arc<Mutex<Option<ResidentWorker>>>);

const MAX_TEXT_FILE_BYTES: u64 = 256 * 1024 * 1024;
// ZIP64 projects are passed by approved path and verified in bounded chunks by
// the worker. Their on-disk size is independent of JSON/text IPC limits.
const MAX_PROJECT_FILE_BYTES: u64 = 16 * 1024 * 1024 * 1024;
const MAX_MCAD_FILE_BYTES: u64 = 2 * 1024 * 1024 * 1024;
const MAX_WORKER_REQUEST_BYTES: usize = 256 * 1024 * 1024;
const MAX_WORKER_STDOUT_BYTES: usize = 256 * 1024 * 1024;
const MAX_WORKER_STDERR_BYTES: usize = 4 * 1024 * 1024;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ActiveWorker {
    operation_id: String,
    method: String,
    started_unix_ms: u128,
    #[serde(skip)]
    cancellation: Arc<AtomicBool>,
}

struct ActiveWorkerGuard {
    state: Arc<Mutex<Option<ActiveWorker>>>,
    operation_id: String,
}

struct ResidentWorker {
    child: Child,
    stdin: Option<ChildStdin>,
    responses: mpsc::Receiver<Result<Vec<u8>, String>>,
    stderr: mpsc::Receiver<(Vec<u8>, bool)>,
}

impl Drop for ResidentWorker {
    fn drop(&mut self) {
        terminate_worker_tree(&mut self.child);
        let _ = self.child.wait();
    }
}

impl ActiveWorkerGuard {
    fn cancellation(&self) -> Arc<AtomicBool> {
        self.state
            .lock()
            .ok()
            .and_then(|active| active.as_ref().map(|item| item.cancellation.clone()))
            .unwrap_or_else(|| Arc::new(AtomicBool::new(false)))
    }
}

impl Drop for ActiveWorkerGuard {
    fn drop(&mut self) {
        if let Ok(mut active) = self.state.lock() {
            if active.as_ref().map(|item| item.operation_id.as_str())
                == Some(self.operation_id.as_str())
            {
                *active = None;
            }
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct OpenedTextFile {
    path: String,
    file_name: String,
    contents: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct SelectedFile {
    path: String,
    file_name: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ResourceSnapshot {
    source: &'static str,
    /// Process-tree CPU normalized to total machine capacity (0..100).
    cpu_percent: Option<f32>,
    core_cpu_percent: Option<f32>,
    system_cpu_percent: Option<f32>,
    /// Aggregate process-tree CPU normalized to total logical CPU capacity.
    capacity_cpu_percent: Option<f32>,
    memory_bytes: u64,
    host_memory_bytes: u64,
    total_memory_bytes: u64,
    system_used_memory_bytes: u64,
    memory_kind: &'static str,
    gpu: gpu_metrics::GpuSnapshot,
    worker_threads: usize,
    logical_cpus: usize,
    process_count: usize,
    worker_active: bool,
}

fn process_belongs_to_tree(system: &System, candidate: Pid, root: Pid) -> bool {
    let mut current = Some(candidate);
    for _ in 0..64 {
        let Some(pid) = current else { return false; };
        if pid == root { return true; }
        current = system.process(pid).and_then(|process| process.parent());
    }
    false
}

fn worker_method(request: &serde_json::Value) -> &str {
    request
        .get("method")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("unknown")
}

fn is_heavy_worker_method(method: &str) -> bool {
    matches!(
        method,
          "benchmarks"
              | "bind_multiboard_coupled_reduced_network"
              | "execute_thermal_field_job"
              | "import_into_assembly_project"
              | "export_mcad_session"
              | "preview_mcad_feedback"
              | "apply_mcad_feedback"
              | "plan_assembly_harnesses"
            | "export_step"
            | "extract_mcad_package_shape_in_project"
            | "generate_mcad_selector_preview_in_project"
            | "mesh_convergence"
            | "prepare_openems_case"
            | "prepare_sparselizard_case"
            | "prepare_3d_scene"
            | "prepare_thermal_case"
            | "prepare_visual_bundle"
            | "read_project_model_artifacts"
            | "read_project_state_artifact"
            | "read_project_visual_bundle"
            | "read_project_package_shape_selector_previews"
            | "tessellate_mcad_part_in_project"
            | "preview_mesh"
            | "run_analysis"
            | "run_converter_study"
            | "run_field_circuit_cosimulation"
            | "run_multiboard_si_independent_batch"
            | "run_openems_case"
            | "run_pi_path_native_mna"
            | "run_harness_pi"
            | "generate_tetrahedral_mesh"
            | "run_preflighted_analysis"
            | "run_si_protocol_test_suite"
            | "run_si_uniform_channel"
            | "run_si_workflow"
            | "run_spice_workspace_native_mna"
            | "run_owned_spice_workspace"
            | "run_sparselizard_case"
            | "run_thermal_case"
    )
}

fn nested_positive_seconds(value: &serde_json::Value, path: &[&str]) -> Option<u64> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_u64().filter(|seconds| *seconds > 0).or_else(|| {
        current
            .as_f64()
            .filter(|seconds| *seconds > 0.0)
            .map(|seconds| seconds.ceil() as u64)
    })
}

fn worker_timeout(request: &serde_json::Value) -> Duration {
    let paths: [&[&str]; 7] = [
        &["params", "timeout_seconds"],
        &["params", "options", "timeout_seconds"],
        &["params", "options", "max_solver_time_s"],
        &["params", "spec", "options", "timeout_seconds"],
        &["params", "spec", "options", "max_solver_time_s"],
        &["params", "spec", "mesh", "max_solver_time_s"],
        &["params", "spec", "transient", "max_solver_time_s"],
    ];
    let requested = paths
        .into_iter()
        .filter_map(|path| nested_positive_seconds(request, path))
        .collect::<Vec<_>>();
    let fallback = if is_heavy_worker_method(worker_method(request)) {
        1_800
    } else {
        180
    };
    let seconds = requested
        .into_iter()
        .max()
        .unwrap_or(fallback)
        .saturating_add(30)
        .clamp(30, 86_400);
    Duration::from_secs(seconds)
}

fn read_capped<R: Read>(mut reader: R, limit: usize) -> (Vec<u8>, bool) {
    let mut bytes = Vec::with_capacity(limit.min(1024 * 1024));
    let mut buffer = [0_u8; 64 * 1024];
    let mut truncated = false;
    loop {
        match reader.read(&mut buffer) {
            Ok(0) | Err(_) => break,
            Ok(count) => {
                let remaining = limit.saturating_sub(bytes.len());
                let accepted = remaining.min(count);
                bytes.extend_from_slice(&buffer[..accepted]);
                truncated |= accepted < count;
            }
        }
    }
    (bytes, truncated)
}

fn read_capped_async<R: Read + Send + 'static>(
    reader: R,
    limit: usize,
) -> mpsc::Receiver<(Vec<u8>, bool)> {
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let _ = sender.send(read_capped(reader, limit));
    });
    receiver
}

fn write_stdin_async(
    mut stdin: ChildStdin,
    input: String,
) -> mpsc::Receiver<(ChildStdin, Result<(), String>)> {
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let result = stdin
            .write_all(input.as_bytes())
            .and_then(|_| stdin.flush())
            .map_err(|error| error.to_string());
        let _ = sender.send((stdin, result));
    });
    receiver
}

fn read_protocol_line_capped<R: BufRead>(
    reader: &mut R,
    limit: usize,
) -> Result<Option<Vec<u8>>, String> {
    let mut line = Vec::with_capacity(limit.min(1024 * 1024));
    loop {
        let available = reader
            .fill_buf()
            .map_err(|error| format!("Unable to read resident SPIKE worker response: {error}"))?;
        if available.is_empty() {
            return if line.is_empty() {
                Ok(None)
            } else {
                Err("Resident SPIKE worker closed stdout mid-response".to_string())
            };
        }
        let newline = available.iter().position(|byte| *byte == b'\n');
        let consumed = newline.map_or(available.len(), |position| position + 1);
        if line.len().saturating_add(consumed) > limit {
            reader.consume(consumed);
            return Err(
                "Resident SPIKE worker response exceeded the desktop safety limit".to_string(),
            );
        }
        line.extend_from_slice(&available[..consumed]);
        reader.consume(consumed);
        if newline.is_some() {
            return Ok(Some(line));
        }
    }
}

fn unix_time_ms() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn claim_heavy_worker(
    state: Arc<Mutex<Option<ActiveWorker>>>,
    request: &serde_json::Value,
) -> Result<Option<ActiveWorkerGuard>, String> {
    let method = worker_method(request);
    if !is_heavy_worker_method(method) {
        return Ok(None);
    }
    let operation_id = request
        .get("id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("unidentified-operation")
        .to_string();
    let mut active = state
        .lock()
        .map_err(|_| "Worker execution state is unavailable".to_string())?;
    if let Some(current) = active.as_ref() {
        return Err(format!(
            "WORKER_BUSY: {} ({}) is already running",
            current.method, current.operation_id
        ));
    }
    *active = Some(ActiveWorker {
        operation_id: operation_id.clone(),
        method: method.to_string(),
        started_unix_ms: unix_time_ms(),
        cancellation: Arc::new(AtomicBool::new(false)),
    });
    drop(active);
    Ok(Some(ActiveWorkerGuard {
        state,
        operation_id,
    }))
}

#[tauri::command]
fn worker_status(
    state: tauri::State<'_, WorkerExecutionState>,
) -> Result<Option<ActiveWorker>, String> {
    state
        .0
        .lock()
        .map(|active| active.clone())
        .map_err(|_| "Worker execution state is unavailable".to_string())
}

#[tauri::command]
fn cancel_worker(
    operation_id: String,
    state: tauri::State<'_, WorkerExecutionState>,
) -> Result<bool, String> {
    let active = state
        .0
        .lock()
        .map_err(|_| "Worker execution state is unavailable".to_string())?;
    let Some(current) = active.as_ref() else {
        return Ok(false);
    };
    if current.operation_id != operation_id {
        return Err(format!(
            "Operation {operation_id} is not the active worker operation"
        ));
    }
    current.cancellation.store(true, Ordering::SeqCst);
    Ok(true)
}

fn normalized_cpu(core_percent: f32, logical_cpus: usize) -> Option<f32> {
    if !core_percent.is_finite() || core_percent < 0.0 { return None; }
    Some((core_percent / logical_cpus.max(1) as f32).clamp(0.0, 100.0))
}

#[tauri::command]
async fn resource_snapshot(
    state: tauri::State<'_, ResourceState>,
    workers: tauri::State<'_, WorkerExecutionState>,
) -> Result<ResourceSnapshot, String> {
    let pid = get_current_pid().map_err(|error| format!("Unable to identify SPIKE: {error}"))?;
    let mut sampler = state.0.lock().map_err(|_| "Resource monitor state is unavailable".to_string())?;
    let now = Instant::now();
    let cpu_ready = sampler.last_sample.is_some_and(|last| now.duration_since(last) >= sysinfo::MINIMUM_CPU_UPDATE_INTERVAL);
    let system = &mut sampler.system;
    system.refresh_memory();
    system.refresh_cpu_usage();
    // Removing dead processes is essential: otherwise every completed worker
    // continues contributing its last CPU and RAM readings indefinitely.
    system.refresh_processes_specifics(ProcessesToUpdate::All, true,
        ProcessRefreshKind::nothing().with_cpu().with_memory());
    let host_memory_bytes = system.process(pid).ok_or("SPIKE process metrics are unavailable")?.memory();
    let logical_cpus = system.cpus().len().max(1);
    let pids: HashSet<_> = system.processes().keys().copied()
        .filter(|candidate| process_belongs_to_tree(system, *candidate, pid)).collect();
    let cpu = pids.iter().filter_map(|pid| system.process(*pid)).map(|p| p.cpu_usage()).sum::<f32>();
    let rss = pids.iter().filter_map(|pid| system.process(*pid)).fold(0_u64, |sum, p| sum.saturating_add(p.memory()));
    let total_memory_bytes = system.total_memory();
    let system_used_memory_bytes = system.used_memory().min(total_memory_bytes);
    let system_cpu = cpu_ready.then(|| normalized_cpu(system.global_cpu_usage(), 1)).flatten();
    let normalized = cpu_ready.then(|| normalized_cpu(cpu, logical_cpus)).flatten();
    let ids = pids.iter().map(|pid| pid.as_u32()).collect();
    let (gpu, private_memory) = sampler.gpu.sample(&ids);
    sampler.last_sample = Some(now);
    Ok(ResourceSnapshot {
        source: "desktop", cpu_percent: normalized, capacity_cpu_percent: normalized, system_cpu_percent: system_cpu,
        core_cpu_percent: normalized.map(|percent| percent * logical_cpus as f32),
        memory_bytes: private_memory.unwrap_or(rss), host_memory_bytes, total_memory_bytes,
        system_used_memory_bytes, memory_kind: if private_memory.is_some() { "private-resident" } else { "aggregate-rss" },
        gpu, worker_threads: worker_thread_budget(), logical_cpus, process_count: pids.len(),
        worker_active: workers.0.lock().map(|active| active.is_some()).unwrap_or(false),
    })
}

fn register_approved_path(
    state: &tauri::State<'_, ApprovedFileState>,
    path: &Path,
) -> Result<PathBuf, String> {
    let normalized = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    state
        .0
        .lock()
        .map_err(|_| "Approved file state is unavailable".to_string())?
        .insert(normalized.clone());
    Ok(normalized)
}

fn selected_startup_project(path: &Path, max_bytes: u64) -> Result<(PathBuf, SelectedFile), String> {
    if !path
        .extension()
        .and_then(OsStr::to_str)
        .is_some_and(|extension| extension.eq_ignore_ascii_case("spike"))
    {
        return Err("Startup projects must use the .spike extension".to_string());
    }
    let canonical = path
        .canonicalize()
        .map_err(|error| format!("Unable to resolve {}: {error}", path.display()))?;
    let metadata = fs::metadata(&canonical)
        .map_err(|error| format!("Unable to inspect {}: {error}", canonical.display()))?;
    if !metadata.is_file() {
        return Err("The startup project is not a regular file".to_string());
    }
    if metadata.len() > max_bytes {
        return Err(format!(
            "{} exceeds the {} MiB desktop project limit",
            canonical.display(), max_bytes / (1024 * 1024)
        ));
    }
    let selected = SelectedFile {
        file_name: canonical
            .file_name()
            .and_then(OsStr::to_str)
            .unwrap_or("project.spike")
            .to_string(),
        path: canonical.to_string_lossy().into_owned(),
    };
    Ok((canonical, selected))
}

fn startup_project_from_args<I>(args: I, max_bytes: u64) -> Option<(PathBuf, SelectedFile)>
where
    I: IntoIterator<Item = OsString>,
{
    let mut candidates = args.into_iter().filter(|argument| {
        Path::new(argument)
            .extension()
            .and_then(OsStr::to_str)
            .is_some_and(|extension| extension.eq_ignore_ascii_case("spike"))
    });
    let candidate = candidates.next()?;
    if candidates.next().is_some() {
        return None;
    }
    selected_startup_project(Path::new(&candidate), max_bytes).ok()
}

#[tauri::command]
fn take_startup_project(
    state: tauri::State<'_, PendingOpenState>,
) -> Result<Option<SelectedFile>, String> {
    state
        .0
        .lock()
        .map(|mut pending| pending.take())
        .map_err(|_| "Startup project state is unavailable".to_string())
}

fn normalized_request_path(value: &str) -> PathBuf {
    let requested = PathBuf::from(value);
    requested.canonicalize().unwrap_or(requested)
}

fn project_worker_paths(request: &serde_json::Value) -> Result<Vec<PathBuf>, String> {
    let params = request
        .get("params")
        .and_then(serde_json::Value::as_object)
        .ok_or("Project worker operations require approved path parameters")?;
    let required_fields: &[&str] = if matches!(worker_method(request), "attach_mcad_part_to_project" | "import_into_assembly_project") {
        &["project_path", "source_path"]
    } else if worker_method(request) == "prepare_visual_bundle" {
        &["board_path"]
    } else if matches!(worker_method(request), "export_mcad_session" | "preview_mcad_feedback" | "apply_mcad_feedback" | "update_mcad_part_in_project" | "reparent_mcad_part_in_project" | "tessellate_mcad_part_in_project" | "extract_mcad_package_shape_in_project" | "generate_mcad_selector_preview_in_project" | "update_assembly_semantics_in_project" | "update_assembly_topology_setup_in_project" | "apply_assembly_geometric_constraint_in_project" | "update_assembly_structure_in_project") {
        &["project_path"]
    } else {
        &["path"]
    };
    let mut paths = required_fields
        .iter()
        .map(|field| {
            params
                .get(*field)
                .and_then(serde_json::Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .map(normalized_request_path)
                .ok_or_else(|| format!("Project worker operation requires approved {field}"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if worker_method(request) == "write_project_package" {
        if let Some(base_path) = params.get("base_package_path").filter(|value| !value.is_null()) {
            let base_path = base_path
                .as_str()
                .filter(|value| !value.trim().is_empty())
                .map(normalized_request_path)
                .ok_or("Project worker operation requires approved base_package_path")?;
            paths.push(base_path);
        }
    }
    if worker_method(request) == "prepare_visual_bundle" {
        if let Some(overrides) = params.get("model_overrides") {
            let values = overrides.as_object().ok_or("Model overrides must be an object")?;
            for value in values.values() {
                let path = value.as_str().ok_or("Model replacement path must be a string")?;
                paths.push(fs::canonicalize(path).map_err(|error| error.to_string())?);
            }
        }
    }
    Ok(paths)
}

fn dialog_for_kind(kind: &str, save: bool) -> rfd::FileDialog {
    let dialog = rfd::FileDialog::new();
    match (kind, save) {
        ("board", false) => dialog.add_filter("KiCad board", &["kicad_pcb"]),
        ("project", _) => dialog.add_filter("SPIKE project", &["spike", "spike.json", "json"]),
        ("report", _) => dialog.add_filter("HTML report", &["html", "htm"]),
        ("step", _) => dialog.add_filter("STEP model", &["step", "stp"]),
        ("netlist", _) => dialog.add_filter("SPICE netlist", &["cir", "sp", "spice", "net"]),
        ("result", _) => dialog.add_filter("SPIKE result bundle", &["spike-results.json", "json"]),
        ("license", _) => dialog.add_filter("SPIKE license", &["license", "spike-license.json", "json", "txt"]),
        _ => dialog.add_filter("Text file", &["txt", "json"]),
    }
}

#[tauri::command]
fn open_text_file(
    kind: String,
    state: tauri::State<'_, ApprovedFileState>,
) -> Result<Option<OpenedTextFile>, String> {
    let Some(path) = dialog_for_kind(&kind, false).pick_file() else {
        return Ok(None);
    };
    let metadata = fs::metadata(&path)
        .map_err(|error| format!("Unable to inspect {}: {error}", path.display()))?;
    if metadata.len() > MAX_TEXT_FILE_BYTES {
        return Err(format!(
            "{} is larger than the 256 MiB desktop text-file limit",
            path.display()
        ));
    }
    let contents = fs::read_to_string(&path)
        .map_err(|error| format!("Unable to read {}: {error}", path.display()))?;
    let approved = register_approved_path(&state, &path)?;
    Ok(Some(OpenedTextFile {
        file_name: approved
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("project.spike")
            .to_string(),
        path: approved.to_string_lossy().into_owned(),
        contents,
    }))
}

#[tauri::command]
fn select_project_file(
    state: tauri::State<'_, ApprovedFileState>,
) -> Result<Option<SelectedFile>, String> {
    let Some(path) = dialog_for_kind("project", false).pick_file() else {
        return Ok(None);
    };
    let metadata = fs::metadata(&path)
        .map_err(|error| format!("Unable to inspect {}: {error}", path.display()))?;
    if !metadata.is_file() {
        return Err("The selected project is not a regular file".to_string());
    }
    if metadata.len() > MAX_PROJECT_FILE_BYTES {
        return Err(format!(
            "{} is larger than the 16 GiB desktop project limit",
            path.display()
        ));
    }
    let approved = register_approved_path(&state, &path)?;
    Ok(Some(SelectedFile {
        file_name: approved
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("project.spike")
            .to_string(),
        path: approved.to_string_lossy().into_owned(),
    }))
}

#[tauri::command]
fn select_mcad_file(
    state: tauri::State<'_, ApprovedFileState>,
) -> Result<Option<SelectedFile>, String> {
    let Some(path) = rfd::FileDialog::new()
        .add_filter("MCAD assembly part", &["step", "stp", "gltf", "glb"])
        .add_filter("PCB component model", &["step", "stp", "wrl", "vrml"])
        .add_filter("Assembly exchange or board", &["spikeassembly", "kicad_pcb", "ipc2581"])
        .pick_file()
    else {
        return Ok(None);
    };
    let metadata = fs::metadata(&path)
        .map_err(|error| format!("Unable to inspect {}: {error}", path.display()))?;
    if !metadata.is_file() {
        return Err("The selected MCAD source is not a regular file".to_string());
    }
    if metadata.len() == 0 || metadata.len() > MAX_MCAD_FILE_BYTES {
        return Err(format!(
            "{} is empty or larger than the 2 GiB MCAD attachment limit",
            path.display()
        ));
    }
    let approved = register_approved_path(&state, &path)?;
    Ok(Some(SelectedFile {
        file_name: approved
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("assembly-part.step")
            .to_string(),
        path: approved.to_string_lossy().into_owned(),
    }))
}

#[tauri::command]
fn select_import_file(kind: String, directory: bool, state: tauri::State<'_, ApprovedFileState>) -> Result<Option<SelectedFile>, String> {
    let dialog = match kind.as_str() {
        "board" => rfd::FileDialog::new().add_filter("CAD board job", &["zip", "tgz", "tar", "gz", "odb", "odb++", "ipc2581"]),
        "harness" => rfd::FileDialog::new().add_filter("Harness connection list", &["json", "csv", "tsv"]),
        _ => return Err("Unknown import source kind".to_string()),
    };
    let selected = if directory { dialog.pick_folder() } else { dialog.pick_file() };
    let Some(path) = selected else { return Ok(None); };
    let approved = register_approved_path(&state, &path)?;
    Ok(Some(SelectedFile { file_name: approved.file_name().and_then(|name| name.to_str()).unwrap_or("source").to_string(), path: approved.to_string_lossy().into_owned() }))
}

#[tauri::command]
fn select_project_save_path(
    suggested_name: String,
    state: tauri::State<'_, ApprovedFileState>,
) -> Result<Option<String>, String> {
    let safe_name = Path::new(&suggested_name)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("project.spike");
    let Some(path) = dialog_for_kind("project", true)
        .set_file_name(safe_name)
        .save_file()
    else {
        return Ok(None);
    };
    let approved = register_approved_path(&state, &path)?;
    Ok(Some(approved.to_string_lossy().into_owned()))
}

#[tauri::command]
fn save_text_file(
    suggested_name: String,
    contents: String,
    kind: String,
    state: tauri::State<'_, ApprovedFileState>,
) -> Result<Option<String>, String> {
    if contents.len() as u64 > MAX_TEXT_FILE_BYTES {
        return Err(
            "The generated file is larger than the 256 MiB desktop text-file limit".to_string(),
        );
    }
    let safe_name = Path::new(&suggested_name)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("spike-output.txt");
    let Some(path) = dialog_for_kind(&kind, true)
        .set_file_name(safe_name)
        .save_file()
    else {
        return Ok(None);
    };
    fs::write(&path, contents.as_bytes())
        .map_err(|error| format!("Unable to write {}: {error}", path.display()))?;
    let approved = register_approved_path(&state, &path)?;
    Ok(Some(approved.to_string_lossy().into_owned()))
}

#[tauri::command]
fn save_extension_artifact(
    suggested_name: String,
    data: String,
    encoding: String,
    sha256: String,
    state: tauri::State<'_, ApprovedFileState>,
) -> Result<Option<String>, String> {
    let payload = extension_artifacts::decode(&data, &encoding, &sha256)?;
    let safe_name = extension_artifacts::file_name(&suggested_name)?;
    let suffix = Path::new(&safe_name).extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase();
    let Some(path) = rfd::FileDialog::new().add_filter("Engineering export", &[suffix.as_str()])
        .set_file_name(&safe_name).save_file() else { return Ok(None); };
    fs::write(&path, payload).map_err(|error| format!("Unable to save artifact: {error}"))?;
    let approved = register_approved_path(&state, &path)?;
    Ok(Some(approved.to_string_lossy().into_owned()))
}

#[tauri::command]
fn write_approved_text_file(
    path: String,
    contents: String,
    state: tauri::State<'_, ApprovedFileState>,
) -> Result<String, String> {
    if contents.len() as u64 > MAX_TEXT_FILE_BYTES {
        return Err(
            "The generated file is larger than the 256 MiB desktop text-file limit".to_string(),
        );
    }
    let requested = PathBuf::from(path);
    let normalized = requested.canonicalize().unwrap_or(requested);
    let approved = state
        .0
        .lock()
        .map_err(|_| "Approved file state is unavailable".to_string())?;
    if !approved.contains(&normalized) {
        return Err(
            "SPIKE will only overwrite a path selected through its native file dialog".to_string(),
        );
    }
    fs::write(&normalized, contents.as_bytes())
        .map_err(|error| format!("Unable to write {}: {error}", normalized.display()))?;
    Ok(normalized.to_string_lossy().into_owned())
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct WorkerLaunchCandidate {
    program: PathBuf,
    args: Vec<String>,
}

fn bundled_worker_candidates(workspace: &Path) -> Vec<PathBuf> {
    #[cfg(target_os = "windows")]
    let executable = "spike-worker.exe";
    #[cfg(not(target_os = "windows"))]
    let executable = "spike-worker";

    vec![
        workspace
            .join("bundled")
            .join("spike-worker")
            .join(executable),
        workspace.join("bundled").join(executable),
    ]
}

fn contains_worker(workspace: &Path) -> bool {
    bundled_worker_candidates(workspace)
        .iter()
        .any(|candidate| candidate.is_file())
        || workspace
            .join("python")
            .join("spike_core")
            .join("service.py")
            .is_file()
}

fn source_workspace() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

fn is_development_source_workspace(workspace: &Path) -> bool {
    if !cfg!(debug_assertions) {
        return false;
    }
    let source = source_workspace();
    let normalized_source = source.canonicalize().unwrap_or(source);
    let normalized_workspace = workspace
        .canonicalize()
        .unwrap_or_else(|_| workspace.to_path_buf());
    normalized_workspace == normalized_source
        && normalized_workspace
            .join("python")
            .join("spike_core")
            .join("service.py")
            .is_file()
}

fn resolve_worker_root(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let mut candidates = Vec::new();
    if let Some(path) = std::env::var_os("SPIKE_WORKSPACE") {
        candidates.push(PathBuf::from(path));
    }
    // Debug builds from a checkout must execute that checkout's current
    // Python sources rather than an older worker copied into target/debug.
    // The compile-time path is trusted; arbitrary directories are accepted
    // only through the existing explicit SPIKE_WORKSPACE override above.
    if cfg!(debug_assertions) {
        candidates.push(source_workspace());
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir);
    }
    if !cfg!(debug_assertions) {
        candidates.push(source_workspace());
    }
    for candidate in candidates {
        let normalized = candidate.canonicalize().unwrap_or(candidate);
        if contains_worker(&normalized) {
            return Ok(normalized);
        }
    }
    Err("Unable to locate the bundled SPIKE Python worker. Set SPIKE_WORKSPACE to a valid installation root.".to_string())
}

fn python_candidates(workspace: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(path) = std::env::var_os("SPIKE_PYTHON") {
        candidates.push(PathBuf::from(path));
    }
    candidates.extend([
        workspace.join(".venv").join("Scripts").join("python.exe"),
        workspace.join(".venv").join("bin").join("python3"),
        workspace.join(".venv").join("bin").join("python"),
        workspace.join("runtime").join("python").join("python.exe"),
        workspace.join("runtime").join("bin").join("python3"),
    ]);
    #[cfg(target_os = "windows")]
    candidates.push(PathBuf::from("python"));
    #[cfg(not(target_os = "windows"))]
    candidates.extend([PathBuf::from("python3"), PathBuf::from("python")]);
    candidates
}

fn worker_launch_candidates(workspace: &Path) -> Vec<WorkerLaunchCandidate> {
    let bundled = bundled_worker_candidates(workspace)
        .into_iter()
        .map(|program| WorkerLaunchCandidate {
            program,
            args: Vec::new(),
        })
        .collect::<Vec<_>>();
    let python = python_candidates(workspace)
        .into_iter()
        .map(|program| WorkerLaunchCandidate {
            program,
            args: vec!["-m".to_string(), "python.spike_core.service".to_string()],
        })
        .collect::<Vec<_>>();
    if is_development_source_workspace(workspace) {
        python.into_iter().chain(bundled).collect()
    } else {
        bundled.into_iter().chain(python).collect()
    }
}

fn worker_thread_budget() -> usize {
    let available = std::thread::available_parallelism().map(|count| count.get()).unwrap_or(1);
    std::env::var("SPIKE_CPU_THREADS").ok().and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0).unwrap_or_else(|| available.saturating_sub(2).max(1))
        .clamp(1, available)
}

fn worker_thread_count() -> String { worker_thread_budget().to_string() }

fn spawn_worker_process(workspace: &Path) -> Result<Child, String> {
    let worker_threads = worker_thread_count();
    let mut launch_errors = Vec::new();
    for candidate in worker_launch_candidates(workspace) {
        if candidate.program.components().count() > 1 && !candidate.program.is_file() {
            continue;
        }
        let mut command = Command::new(&candidate.program);
        command
            .args(&candidate.args)
            .current_dir(workspace)
            .env("SPIKE_HOME", workspace)
            .env("SPIKE_WORKSPACE", workspace)
            .env("PYTHONNOUSERSITE", "1")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .env("PYTHONUTF8", "1")
            .env("SPIKE_CPU_THREADS", &worker_threads)
            .env("NUMBA_NUM_THREADS", &worker_threads)
            .env("VECLIB_MAXIMUM_THREADS", &worker_threads)
            .env("OMP_MAX_ACTIVE_LEVELS", "1")
            .env("OMP_NUM_THREADS", &worker_threads)
            .env("OPENBLAS_NUM_THREADS", &worker_threads)
            .env("MKL_NUM_THREADS", &worker_threads)
            .env("NUMEXPR_NUM_THREADS", &worker_threads)
            .env("NUMEXPR_MAX_THREADS", &worker_threads)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(target_os = "windows")]
        command.creation_flags(CREATE_NO_WINDOW);
        match command.spawn() {
            Ok(process) => return Ok(process),
            Err(error) => launch_errors.push(format!("{}: {error}", candidate.program.display())),
        }
    }
    Err(format!(
        "Unable to start the packaged SPIKE worker. Development builds may set SPIKE_PYTHON to an approved Python 3 runtime. Attempts: {}",
        launch_errors.join("; ")
    ))
}

fn is_resident_worker_method(method: &str) -> bool {
    matches!(
        method,
        "spikes_session_create"
            | "spikes_session_step"
            | "spikes_session_checkpoint"
            | "spikes_session_restore"
            | "spikes_session_close"
    )
}

fn spawn_resident_worker(workspace: &Path) -> Result<ResidentWorker, String> {
    let mut child = spawn_worker_process(workspace)?;
    let stdin = child
        .stdin
        .take()
        .ok_or("Resident SPIKE worker stdin is unavailable")?;
    let stdout = child
        .stdout
        .take()
        .ok_or("Resident SPIKE worker stdout is unavailable")?;
    let stderr = child
        .stderr
        .take()
        .ok_or("Resident SPIKE worker stderr is unavailable")?;

    let (response_sender, responses) = mpsc::channel();
    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        loop {
            match read_protocol_line_capped(&mut reader, MAX_WORKER_STDOUT_BYTES) {
                Ok(None) => {
                    let _ = response_sender.send(Err(
                        "Resident SPIKE worker closed stdout before responding".to_string(),
                    ));
                    break;
                }
                Ok(Some(line)) => {
                    if response_sender.send(Ok(line)).is_err() {
                        break;
                    }
                }
                Err(error) => {
                    let _ = response_sender.send(Err(error));
                    break;
                }
            }
        }
    });

    let (stderr_sender, stderr_receiver) = mpsc::channel();
    thread::spawn(move || {
        let _ = stderr_sender.send(read_capped(stderr, MAX_WORKER_STDERR_BYTES));
    });

    Ok(ResidentWorker {
        child,
        stdin: Some(stdin),
        responses,
        stderr: stderr_receiver,
    })
}

fn resident_worker_failure_detail(worker: &ResidentWorker) -> String {
    match worker.stderr.try_recv() {
        Ok((bytes, truncated)) => {
            let mut detail = String::from_utf8_lossy(&bytes).trim().to_string();
            if truncated {
                detail.push_str(" [stderr truncated]");
            }
            detail
        }
        Err(_) => String::new(),
    }
}

fn run_resident_worker_request(
    workspace: &Path,
    state: &Arc<Mutex<Option<ResidentWorker>>>,
    request: serde_json::Value,
    cancellation: Option<Arc<AtomicBool>>,
) -> Result<serde_json::Value, String> {
    if cancellation
        .as_ref()
        .is_some_and(|flag| flag.load(Ordering::SeqCst))
    {
        return Err("SPIKE worker operation was cancelled".to_string());
    }
    let input = format!(
        "{}\n",
        serde_json::to_string(&request).map_err(|error| error.to_string())?
    );
    if input.len() > MAX_WORKER_REQUEST_BYTES {
        return Err("SPIKE worker request exceeds the 256 MiB safety limit".to_string());
    }
    let expected_id = request.get("id").cloned();
    let timeout = worker_timeout(&request);
    let mut resident = state
        .lock()
        .map_err(|_| "Resident SPIKE worker state is unavailable".to_string())?;
    if resident.is_none() {
        *resident = Some(spawn_resident_worker(workspace)?);
    }
    if cancellation
        .as_ref()
        .is_some_and(|flag| flag.load(Ordering::SeqCst))
    {
        *resident = None;
        return Err("SPIKE worker operation was cancelled".to_string());
    }
    let worker = resident
        .as_mut()
        .ok_or("Resident SPIKE worker is unavailable")?;
    if let Some(status) = worker.child.try_wait().map_err(|error| error.to_string())? {
        let detail = resident_worker_failure_detail(worker);
        *resident = None;
        return Err(format!(
            "Resident SPIKE worker exited before the request ({status}){}",
            if detail.is_empty() { String::new() } else { format!(": {detail}") }
        ));
    }
    let started = Instant::now();
    let stdin = worker.stdin.take().ok_or("Resident SPIKE worker stdin is busy")?;
    let write_receiver = write_stdin_async(stdin, input);
    let mut write_pending = true;
    let line = loop {
        if cancellation
            .as_ref()
            .is_some_and(|flag| flag.load(Ordering::SeqCst))
        {
            *resident = None;
            return Err("SPIKE worker operation was cancelled".to_string());
        }
        if started.elapsed() >= timeout {
            *resident = None;
            return Err(format!(
                "Resident SPIKE worker exceeded its {:.0} second watchdog",
                timeout.as_secs_f64()
            ));
        }
        if write_pending {
            match write_receiver.try_recv() {
                Ok((stdin, Ok(()))) => {
                    worker.stdin = Some(stdin);
                    write_pending = false;
                }
                Ok((_stdin, Err(error))) => {
                    let detail = resident_worker_failure_detail(worker);
                    *resident = None;
                    return Err(format!(
                        "Unable to write resident SPIKE worker request: {error}{}",
                        if detail.is_empty() { String::new() } else { format!(": {detail}") }
                    ));
                }
                Err(mpsc::TryRecvError::Empty) => {
                    thread::sleep(Duration::from_millis(10));
                    continue;
                }
                Err(mpsc::TryRecvError::Disconnected) => {
                    *resident = None;
                    return Err("Resident SPIKE worker stdin writer stopped unexpectedly".to_string());
                }
            }
        }
        match worker.responses.recv_timeout(Duration::from_millis(50)) {
            Ok(Ok(line)) => break line,
            Ok(Err(error)) => {
                let detail = resident_worker_failure_detail(worker);
                *resident = None;
                return Err(if detail.is_empty() {
                    error
                } else {
                    format!("{error}: {detail}")
                });
            }
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                let detail = resident_worker_failure_detail(worker);
                *resident = None;
                return Err(format!(
                    "Resident SPIKE worker response channel closed{}",
                    if detail.is_empty() { String::new() } else { format!(": {detail}") }
                ));
            }
        }
    };
    let response: serde_json::Value = match serde_json::from_slice(&line) {
        Ok(response) => response,
        Err(error) => {
            *resident = None;
            return Err(format!("Invalid resident worker response: {error}"));
        }
    };
    if expected_id.is_some() && response.get("id") != expected_id.as_ref() {
        *resident = None;
        return Err("Resident SPIKE worker response ID does not match the request".to_string());
    }
    Ok(response)
}

fn terminate_worker_tree(child: &mut Child) {
    #[cfg(target_os = "windows")]
    {
        // Preserve descendant cleanup without allowing taskkill itself to make
        // a user cancellation wait indefinitely.
        if let Ok(mut killer) = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
        {
            let deadline = Instant::now() + Duration::from_millis(750);
            loop {
                match killer.try_wait() {
                    Ok(Some(_)) => break,
                    Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(10)),
                    _ => {
                        let _ = killer.kill();
                        let _ = killer.wait();
                        break;
                    }
                }
            }
        }
    }
    let _ = child.kill();
}

fn run_worker_process(
    app: tauri::AppHandle,
    request: serde_json::Value,
    cancellation: Option<Arc<AtomicBool>>,
) -> Result<serde_json::Value, String> {
    // Stop pressed during capability checks / blocking-task scheduling must not
    // start a process that the user has already cancelled.
    if cancellation
        .as_ref()
        .is_some_and(|flag| flag.load(Ordering::SeqCst))
    {
        return Err("SPIKE worker operation was cancelled".to_string());
    }
    let workspace = resolve_worker_root(&app)?;
    let input = format!(
        "{}\n",
        serde_json::to_string(&request).map_err(|error| error.to_string())?
    );
    if input.len() > MAX_WORKER_REQUEST_BYTES {
        return Err("SPIKE worker request exceeds the 256 MiB safety limit".to_string());
    }
    let mut child = spawn_worker_process(&workspace)?;
    if cancellation
        .as_ref()
        .is_some_and(|flag| flag.load(Ordering::SeqCst))
    {
        terminate_worker_tree(&mut child);
        let _ = child.wait();
        return Err("SPIKE worker operation was cancelled".to_string());
    }
    let stdout = child.stdout.take().ok_or("Worker stdout is unavailable")?;
    let stderr = child.stderr.take().ok_or("Worker stderr is unavailable")?;
    let stdout_reader = read_capped_async(stdout, MAX_WORKER_STDOUT_BYTES);
    let stderr_reader = read_capped_async(stderr, MAX_WORKER_STDERR_BYTES);
    let stdin = child.stdin.take().ok_or("Worker stdin is unavailable")?;
    let write_receiver = write_stdin_async(stdin, input);

    let timeout = worker_timeout(&request);
    let started = Instant::now();
    let mut write_pending = true;
    let (status, timed_out) = loop {
        if write_pending {
            match write_receiver.try_recv() {
                Ok((_stdin, Ok(()))) => write_pending = false,
                Ok((_stdin, Err(error))) => {
                    terminate_worker_tree(&mut child);
                    let _ = child.wait();
                    return Err(format!("Unable to write SPIKE worker request: {error}"));
                }
                Err(mpsc::TryRecvError::Disconnected) => {
                    terminate_worker_tree(&mut child);
                    let _ = child.wait();
                    return Err("SPIKE worker stdin writer stopped unexpectedly".to_string());
                }
                Err(mpsc::TryRecvError::Empty) => {}
            }
        }
        match child.try_wait().map_err(|error| error.to_string())? {
            Some(status) => break (status, false),
            None if cancellation
                .as_ref()
                .is_some_and(|flag| flag.load(Ordering::SeqCst)) =>
            {
                terminate_worker_tree(&mut child);
                let _ = child.wait();
                return Err("SPIKE worker operation was cancelled".to_string());
            }
            None if started.elapsed() >= timeout => {
                terminate_worker_tree(&mut child);
                let status = child.wait().map_err(|error| error.to_string())?;
                break (status, true);
            }
            None => thread::sleep(Duration::from_millis(50)),
        }
    };
    let output_deadline = if timed_out { Duration::from_secs(1) } else { Duration::from_secs(5) };
    let (stdout, stdout_truncated) = stdout_reader.recv_timeout(output_deadline)
        .map_err(|_| "Worker stdout did not close after process exit".to_string())?;
    let (stderr, stderr_truncated) = stderr_reader.recv_timeout(output_deadline)
        .map_err(|_| "Worker stderr did not close after process exit".to_string())?;
    if timed_out {
        return Err(format!(
            "SPIKE worker exceeded its {:.0} second watchdog",
            timeout.as_secs_f64()
        ));
    }
    if stdout_truncated || stderr_truncated {
        return Err("SPIKE worker output exceeded the desktop safety limit".to_string());
    }
    if !status.success() {
        return Err(format!(
            "SPIKE worker failed: {}",
            String::from_utf8_lossy(&stderr)
        ));
    }
    let line = String::from_utf8(stdout).map_err(|error| error.to_string())?;
    serde_json::from_str(line.trim()).map_err(|error| format!("Invalid worker response: {error}"))
}

#[tauri::command]
async fn run_worker(
    app: tauri::AppHandle,
    request: serde_json::Value,
    state: tauri::State<'_, WorkerExecutionState>,
    resident: tauri::State<'_, ResidentWorkerState>,
) -> Result<serde_json::Value, String> {
    require_worker_capability(&app, &request)?;
    let guard = claim_heavy_worker(state.0.clone(), &request)?;
    let cancellation = guard.as_ref().map(ActiveWorkerGuard::cancellation);
    let resident_state = resident.0.clone();
    let use_resident = is_resident_worker_method(worker_method(&request));
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = guard;
        if use_resident {
            let workspace = resolve_worker_root(&app)?;
            run_resident_worker_request(&workspace, &resident_state, request, cancellation)
        } else {
            run_worker_process(app, request, cancellation)
        }
    })
    .await
    .map_err(|error| format!("SPIKE worker task failed: {error}"))?
}

#[tauri::command]
async fn run_project_worker(
    app: tauri::AppHandle,
    request: serde_json::Value,
    files: tauri::State<'_, ApprovedFileState>,
    workers: tauri::State<'_, WorkerExecutionState>,
    trust: tauri::State<'_, project_trust_binding::ProjectManifestState>,
) -> Result<serde_json::Value, String> {
    require_worker_capability(&app, &request)?;
    let method = worker_method(&request).to_string();
    let requested_paths = project_worker_paths(&request)?;
    let all_approved = {
        let approved = files
            .0
            .lock()
            .map_err(|_| "Approved file state is unavailable".to_string())?;
        requested_paths.iter().all(|path| approved.contains(path))
    };
    if !all_approved {
        return Err(
            "SPIKE project and MCAD access is limited to paths selected through their native file dialogs"
                .to_string(),
        );
    }
    let project_path = requested_paths
        .first()
        .ok_or_else(|| "Project worker operation has no approved project path".to_string())?
        .clone();
    project_trust_binding::require_targeted_read_binding(
        &method, &request, &project_path, &trust,
    )?;
    let guard = claim_heavy_worker(workers.0.clone(), &request)?;
    let cancellation = guard.as_ref().map(ActiveWorkerGuard::cancellation);
    let response = tauri::async_runtime::spawn_blocking(move || {
        let _guard = guard;
        run_worker_process(app, request, cancellation)
    })
    .await
    .map_err(|error| format!("SPIKE project worker task failed: {error}"))??;
    project_trust_binding::update_from_worker_response(
        &method, &project_path, &response, &trust,
    )?;
    Ok(response)
}

fn require_worker_capability(
    app: &tauri::AppHandle,
    request: &serde_json::Value,
) -> Result<(), String> {
    let capability = entitlement::capability_for_worker(request);
    if capability == "project.read" {
        return Ok(());
    }
    let license = entitlement::status(app);
    if license.permits(capability) {
        Ok(())
    } else {
        Err(format!(
            "SPIKE-BE-SECURITY-E-0006: a valid license with capability '{capability}' is required ({})",
            license.message.as_deref().unwrap_or("license unavailable")
        ))
    }
}

#[tauri::command]
fn license_status(app: tauri::AppHandle) -> entitlement::LicenseSummary {
    entitlement::status(&app)
}

#[tauri::command]
fn license_device_request() -> entitlement::DeviceBindingSummary {
    entitlement::device_request()
}

#[tauri::command]
fn license_activate(
    app: tauri::AppHandle,
    entitlement_json: String,
) -> Result<entitlement::LicenseSummary, String> {
    entitlement::activate(&app, &entitlement_json)
}

#[tauri::command]
fn license_deactivate(app: tauri::AppHandle) -> Result<entitlement::LicenseSummary, String> {
    entitlement::deactivate(&app)
}

#[tauri::command]
fn license_file_export(app: tauri::AppHandle) -> Result<String, String> {
    entitlement::export(&app)
}

#[tauri::command]
fn verify_project_manifest_signature(
    signed_payload_base64url: String,
    signature: package_trust::PackageSignatureEnvelope,
) -> Result<package_trust::PackageTrustSummary, String> {
    package_trust::verify(&signed_payload_base64url, &signature)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let startup_project = startup_project_from_args(std::env::args_os().skip(1), MAX_PROJECT_FILE_BYTES);
    let mut approved_paths = HashSet::new();
    if let Some((path, _)) = startup_project.as_ref() {
        approved_paths.insert(path.clone());
    }
    let pending_project = startup_project.map(|(_, selected)| selected);
    tauri::Builder::default()
        .manage(ResourceState(Mutex::new(ResourceSampler { system: System::new(), gpu: gpu_metrics::Sampler::default(), last_sample: None })))
        .manage(ApprovedFileState(Mutex::new(approved_paths)))
        .manage(PendingOpenState(Mutex::new(pending_project)))
        .manage(WorkerExecutionState(Arc::new(Mutex::new(None))))
        .manage(ResidentWorkerState(Arc::new(Mutex::new(None))))
        .manage(project_trust_binding::ProjectManifestState::new())
        .invoke_handler(tauri::generate_handler![
            run_worker,
            run_project_worker,
            worker_status,
            cancel_worker,
            resource_snapshot,
            open_text_file,
            select_project_file,
            take_startup_project,
            select_mcad_file,
            select_import_file,
            select_project_save_path,
            save_text_file,
            save_extension_artifact,
            write_approved_text_file,
            license_status,
            license_device_request,
            license_activate,
            license_deactivate,
            license_file_export,
            verify_project_manifest_signature
        ])
        .run(tauri::generate_context!())
        .expect("error while running SPIKE desktop application");
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn cpu_readings_use_machine_capacity_and_reject_invalid_samples() {
        assert_eq!(normalized_cpu(1600.0, 32), Some(50.0));
        assert_eq!(normalized_cpu(4000.0, 32), Some(100.0));
        assert_eq!(normalized_cpu(0.0, 1), Some(0.0));
        assert_eq!(normalized_cpu(f32::NAN, 8), None);
        assert_eq!(normalized_cpu(f32::INFINITY, 8), None);
        assert_eq!(normalized_cpu(-1.0, 8), None);
    }

    fn temporary_startup_project(name: &str, contents: &[u8]) -> PathBuf {
        let unique = format!(
            "spike-startup-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        );
        let directory = std::env::temp_dir().join(unique);
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join(name);
        fs::write(&path, contents).unwrap();
        path
    }

    #[test]
    fn startup_project_accepts_one_canonical_bounded_spike_file() {
        let path = temporary_startup_project("assembly.SPIKE", b"fixture");
        let (canonical, selected) = startup_project_from_args(
            [path.as_os_str().to_os_string()],
            MAX_TEXT_FILE_BYTES,
        )
        .expect("valid startup project");
        assert_eq!(canonical, path.canonicalize().unwrap());
        assert_eq!(selected.path, canonical.to_string_lossy());
        assert!(selected.file_name.eq_ignore_ascii_case("assembly.SPIKE"));
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }

    #[test]
    fn startup_project_accepts_package_above_text_transport_limit() {
        let path = temporary_startup_project("large.spike", b"PK\x03\x04");
        fs::OpenOptions::new().write(true).open(&path).unwrap()
            .set_len(MAX_TEXT_FILE_BYTES + 1).unwrap();
        assert!(selected_startup_project(&path, MAX_TEXT_FILE_BYTES).is_err());
        assert!(selected_startup_project(&path, MAX_PROJECT_FILE_BYTES).is_ok());
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }

    #[test]
    fn startup_project_rejects_ambiguous_wrong_extension_and_oversized_inputs() {
        let path = temporary_startup_project("assembly.spike", b"fixture");
        assert!(startup_project_from_args(
            [path.as_os_str().to_os_string(), path.as_os_str().to_os_string()],
            MAX_TEXT_FILE_BYTES,
        )
        .is_none());
        let wrong_extension = path.with_extension("json");
        fs::write(&wrong_extension, b"fixture").unwrap();
        assert!(startup_project_from_args(
            [wrong_extension.as_os_str().to_os_string()],
            MAX_TEXT_FILE_BYTES,
        )
        .is_none());
        assert!(startup_project_from_args([path.as_os_str().to_os_string()], 1).is_none());
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }

    #[test]
    fn heavy_worker_methods_are_explicit() {
        assert!(is_heavy_worker_method("run_analysis"));
        assert!(is_heavy_worker_method("preview_mesh"));
        assert!(is_heavy_worker_method("prepare_openems_case"));
        assert!(is_heavy_worker_method("run_openems_case"));
        assert!(is_heavy_worker_method("run_si_uniform_channel"));
        assert!(is_heavy_worker_method("run_si_protocol_test_suite"));
        assert!(is_heavy_worker_method("prepare_sparselizard_case"));
        assert!(is_heavy_worker_method("run_sparselizard_case"));
        assert!(is_heavy_worker_method("run_converter_study"));
        assert!(is_heavy_worker_method("run_field_circuit_cosimulation"));
        assert!(is_heavy_worker_method("run_multiboard_si_independent_batch"));
        assert!(is_heavy_worker_method("run_pi_path_native_mna"));
        assert!(is_heavy_worker_method("execute_thermal_field_job"));
        assert!(is_heavy_worker_method("bind_multiboard_coupled_reduced_network"));
        assert!(is_heavy_worker_method("run_spice_workspace_native_mna"));
        assert!(is_heavy_worker_method("run_owned_spice_workspace"));
        assert!(is_heavy_worker_method("read_project_model_artifacts"));
        assert!(is_heavy_worker_method("read_project_state_artifact"));
        assert!(is_heavy_worker_method("read_project_visual_bundle"));
        assert!(is_heavy_worker_method("read_project_package_shape_selector_previews"));
        assert!(is_heavy_worker_method("extract_mcad_package_shape_in_project"));
        assert!(is_heavy_worker_method("generate_mcad_selector_preview_in_project"));
        assert!(!is_heavy_worker_method("dependencies"));
    }

    #[test]
    fn claimed_worker_exposes_cancellation_before_process_start() {
        let state = Arc::new(Mutex::new(None));
        let guard = claim_heavy_worker(
            state.clone(),
            &json!({"id": "cancel-during-startup", "method": "run_analysis"}),
        )
        .unwrap()
        .unwrap();
        let cancellation = guard.cancellation();
        {
            let active = state.lock().unwrap();
            active.as_ref().unwrap().cancellation.store(true, Ordering::SeqCst);
        }
        assert!(cancellation.load(Ordering::SeqCst));
        drop(guard);
        assert!(state.lock().unwrap().is_none());
    }

    #[test]
    fn interactive_spikes_methods_are_the_only_resident_worker_routes() {
        for method in [
            "spikes_session_create",
            "spikes_session_step",
            "spikes_session_checkpoint",
            "spikes_session_restore",
            "spikes_session_close",
        ] {
            assert!(is_resident_worker_method(method), "{method}");
        }
        assert!(!is_resident_worker_method("spikes_engine_status"));
        assert!(!is_resident_worker_method("spikes_run_netlist"));
        assert!(!is_resident_worker_method("run_analysis"));
    }

    #[test]
    fn requested_solver_time_extends_the_watchdog() {
        let request = json!({
            "method": "run_analysis",
            "params": { "spec": { "mesh": { "max_solver_time_s": 7200 } } }
        });
        assert_eq!(worker_timeout(&request), Duration::from_secs(7230));
    }

    #[test]
    fn worker_output_is_capped_but_fully_drained() {
        let (output, truncated) = read_capped(&b"0123456789"[..], 4);
        assert_eq!(output, b"0123");
        assert!(truncated);

        let mut bounded_line = BufReader::new(&b"0123456789\n"[..]);
        assert!(read_protocol_line_capped(&mut bounded_line, 4)
            .unwrap_err()
            .contains("safety limit"));
        let mut complete_line = BufReader::new(&b"{}\n"[..]);
        assert_eq!(
            read_protocol_line_capped(&mut complete_line, 4).unwrap(),
            Some(b"{}\n".to_vec())
        );
    }

    #[test]
    fn terminating_an_unreading_child_releases_a_blocked_stdin_writer() {
        #[cfg(target_os = "windows")]
        let mut child = Command::new("powershell")
            .args(["-NoProfile", "-Command", "Start-Sleep -Seconds 30"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        #[cfg(not(target_os = "windows"))]
        let mut child = Command::new("sh")
            .args(["-c", "sleep 30"])
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();

        let stdin = child.stdin.take().unwrap();
        let writer = write_stdin_async(stdin, "x".repeat(16 * 1024 * 1024));
        thread::sleep(Duration::from_millis(50));
        terminate_worker_tree(&mut child);
        let _ = child.wait();
        assert!(writer.recv_timeout(Duration::from_secs(2)).is_ok());
    }

    #[test]
    fn project_worker_path_contract_requires_both_mcad_paths() {
        let request = json!({
            "method": "attach_mcad_part_to_project",
            "params": { "project_path": "fixture.spike", "source_path": "case.step" }
        });
        assert_eq!(project_worker_paths(&request).unwrap().len(), 2);
        let missing_source = json!({
            "method": "attach_mcad_part_to_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert!(project_worker_paths(&missing_source)
            .unwrap_err()
            .contains("source_path"));
        let ordinary = json!({
            "method": "read_project_package",
            "params": { "path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&ordinary).unwrap().len(), 1);
        let board_visual = json!({
            "method": "prepare_visual_bundle",
            "params": { "board_path": "selected.kicad_pcb" }
        });
        assert_eq!(project_worker_paths(&board_visual).unwrap().len(), 1);
        let replacement_visual = json!({
            "method": "prepare_visual_bundle",
            "params": { "board_path": "selected.kicad_pcb", "model_overrides": { "missing.step": "Cargo.toml" } }
        });
        assert_eq!(project_worker_paths(&replacement_visual).unwrap().len(), 2);
        let malformed_replacement = json!({
            "method": "prepare_visual_bundle",
            "params": { "board_path": "selected.kicad_pcb", "model_overrides": { "missing.step": 42 } }
        });
        assert!(project_worker_paths(&malformed_replacement).is_err());
        let placement_edit = json!({
            "method": "update_mcad_part_in_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&placement_edit).unwrap().len(), 1);
        let semantics_edit = json!({
            "method": "update_assembly_semantics_in_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&semantics_edit).unwrap().len(), 1);
        let exact_shape = json!({
            "method": "extract_mcad_package_shape_in_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&exact_shape).unwrap().len(), 1);
        let selector_preview = json!({
            "method": "generate_mcad_selector_preview_in_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&selector_preview).unwrap().len(), 1);
        let topology_setup = json!({
            "method": "update_assembly_topology_setup_in_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&topology_setup).unwrap().len(), 1);
        let geometric_snap = json!({
            "method": "apply_assembly_geometric_constraint_in_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&geometric_snap).unwrap().len(), 1);
        let assembly_structure = json!({
            "method": "update_assembly_structure_in_project",
            "params": { "project_path": "fixture.spike" }
        });
        assert_eq!(project_worker_paths(&assembly_structure).unwrap().len(), 1);
        for method in ["export_mcad_session", "preview_mcad_feedback", "apply_mcad_feedback"] {
            let request = json!({"method": method, "params": {"project_path": "fixture.spike"}});
            assert_eq!(project_worker_paths(&request).unwrap().len(), 1);
            assert!(project_trust_binding::is_targeted_project_read(method));
            assert!(is_heavy_worker_method(method));
        }
        assert_eq!(entitlement::capability_for_worker(&json!({"method": "apply_mcad_feedback"})), "project.write");

        let lossless_resave = json!({
            "method": "write_project_package",
            "params": {
                "path": "saved.spike",
                "base_package_path": "opened.spike"
            }
        });
        assert_eq!(project_worker_paths(&lossless_resave).unwrap().len(), 2);
        let new_package = json!({
            "method": "write_project_package",
            "params": { "path": "saved.spike", "base_package_path": null }
        });
        assert_eq!(project_worker_paths(&new_package).unwrap().len(), 1);
        let empty_base = json!({
            "method": "write_project_package",
            "params": { "path": "saved.spike", "base_package_path": "" }
        });
        assert!(project_worker_paths(&empty_base)
            .unwrap_err()
            .contains("base_package_path"));
    }

    #[test]
    fn packaged_worker_precedes_python_for_non_source_workspaces() {
        let workspace = Path::new("fixture-root");
        let candidates = worker_launch_candidates(workspace);
        assert!(candidates[0].program.to_string_lossy().contains("bundled"));
        assert!(candidates[0].args.is_empty());
        assert!(candidates
            .iter()
            .any(|candidate| candidate.args == ["-m", "python.spike_core.service"]));
    }

    #[cfg(debug_assertions)]
    #[test]
    fn source_python_precedes_stale_packaged_worker_in_debug_checkout() {
        let workspace = source_workspace().canonicalize().expect("source workspace");
        let candidates = worker_launch_candidates(&workspace);
        assert_eq!(candidates[0].args, ["-m", "python.spike_core.service"],);
        assert!(candidates
            .iter()
            .any(|candidate| candidate.program.to_string_lossy().contains("bundled")));
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn resident_packaged_worker_preserves_a_native_spikes_session() {
        let workspace = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .canonicalize()
            .expect("workspace root");
        let packaged_worker = workspace
            .join("app")
            .join("src-tauri")
            .join("resources")
            .join("worker")
            .join("spike-worker")
            .join("spike-worker.exe");
        assert!(packaged_worker.is_file(), "{}", packaged_worker.display());

        let state = Arc::new(Mutex::new(None));
        let netlist = "* resident RC probe\nVdrive in 0 0\nR1 in out 1k\nC1 out 0 1u\n.tran 100u 2m\n.end\n";
        let created = run_resident_worker_request(
            &workspace,
            &state,
            json!({
                "id": "resident-create",
                "method": "spikes_session_create",
                "params": {
                    "netlist": netlist,
                    "probes": ["V(out)"],
                    "integration_method": "backward_euler"
                }
            }),
            None,
        )
        .expect("create resident session");
        assert_eq!(created["ok"], true);
        let session_id = created["result"]["session_id"]
            .as_str()
            .expect("session id")
            .to_string();
        let original_pid = state
            .lock()
            .unwrap()
            .as_ref()
            .expect("resident worker")
            .child
            .id();

        let stepped = run_resident_worker_request(
            &workspace,
            &state,
            json!({
                "id": "resident-step",
                "method": "spikes_session_step",
                "params": {
                    "session_id": session_id,
                    "source_values": {"Vdrive": 1.0},
                    "steps": 10,
                    "capture": "last"
                }
            }),
            None,
        )
        .expect("step resident session");
        assert_eq!(stepped["ok"], true);
        let observed = stepped["result"]["samples"][0]["values"]["V(out)"]
            .as_f64()
            .expect("RC sample");
        let expected = 1.0_f64 - (1.0_f64 / 1.1_f64).powi(10);
        assert!((observed - expected).abs() <= 1.0e-12);
        assert_eq!(
            state.lock().unwrap().as_ref().unwrap().child.id(),
            original_pid
        );

        let checkpointed = run_resident_worker_request(
            &workspace,
            &state,
            json!({
                "id": "resident-checkpoint",
                "method": "spikes_session_checkpoint",
                "params": {"session_id": session_id}
            }),
            None,
        )
        .expect("checkpoint resident session");
        let checkpoint_id = checkpointed["result"]["checkpoint_id"]
            .as_str()
            .expect("checkpoint id")
            .to_string();
        run_resident_worker_request(
            &workspace,
            &state,
            json!({
                "id": "resident-perturb",
                "method": "spikes_session_step",
                "params": {
                    "session_id": session_id,
                    "source_values": {"Vdrive": -1.0},
                    "steps": 3
                }
            }),
            None,
        )
        .expect("perturb resident session");
        let restored = run_resident_worker_request(
            &workspace,
            &state,
            json!({
                "id": "resident-restore",
                "method": "spikes_session_restore",
                "params": {
                    "session_id": session_id,
                    "checkpoint_id": checkpoint_id
                }
            }),
            None,
        )
        .expect("restore resident session");
        assert_eq!(
            restored["result"]["sample"]["values"]["V(out)"]
                .as_f64()
                .expect("restored RC sample"),
            observed
        );

        let closed = run_resident_worker_request(
            &workspace,
            &state,
            json!({
                "id": "resident-close",
                "method": "spikes_session_close",
                "params": {"session_id": session_id}
            }),
            None,
        )
        .expect("close resident session");
        assert_eq!(closed["result"]["status"], "closed");
        *state.lock().unwrap() = None;
    }
}
