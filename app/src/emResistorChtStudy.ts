// SPDX-License-Identifier: Apache-2.0
import type { SimulationStudy, SimulationStudyCase, StudyRun } from "./simulationStudies";

export const EM_RESISTOR_CHT_STUDY_TYPE = "em-resistor-cht";

/** A reviewed runner draft, never an automatic solver invocation. Python owns admission. */
export function emResistorChtStudyRunner(study?: SimulationStudy): string {
  const embedded = JSON.stringify(JSON.stringify(study ?? null));
  return `# Explicit experimental AC resistor / CHT study. Review inputs before Run.
import json
from pathlib import Path

STUDY = json.loads(${embedded})
REQUEST_FILE = None  # Worker-parameter JSON containing exactly {"request": ...}
STUDY_INPUT = None  # Previously exported study JSON; choose this OR REQUEST_FILE
STUDY_FILE = None  # Optional NEW output path; import it in Simulation studies, then save .spike
RESULT_FILE = None  # Optional NEW result-only output path
MAX_FILE_BYTES = 3 * 1024 * 1024

def read_json(path):
    path = Path(path).expanduser().resolve()
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Study/request file exceeds 3 MiB")
    return json.loads(path.read_text(encoding="utf-8"))

def write_new(path, value):
    text = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Export exceeds 3 MiB")
    with Path(path).expanduser().resolve().open("x", encoding="utf-8") as stream:
        stream.write(text)

if REQUEST_FILE is not None and STUDY_INPUT is not None:
    raise ValueError("Choose exactly one request or study input")
if STUDY_INPUT is not None:
    if STUDY is not None:
        raise ValueError("An embedded study and STUDY_INPUT are ambiguous")
    STUDY = read_json(STUDY_INPUT)
if REQUEST_FILE is not None:
    params = read_json(REQUEST_FILE)
    if not isinstance(params, dict) or set(params) != {"request"}:
        raise ValueError("Request file requires exactly one request field")
    request = params["request"]
elif STUDY is not None:
    cases = STUDY.get("cases", [])
    if len(cases) != 1 or cases[0].get("type") != "em-resistor-cht":
        raise ValueError("Select exactly one AC/CHT case")
    request = cases[0]["settings"]["request"]
else:
    request = None

if request is None:
    print("Set REQUEST_FILE or STUDY_INPUT; nothing was launched.")
else:
    payload = {"request": request}
    if STUDY is not None:
        payload["study"] = STUDY
    prepared = spike.call("prepare_em_resistor_cht_study", {"request": payload})
    # Structural and target admission finishes before the numerical call.
    result = spike.call("run_em_network_resistor_cht", {"request": prepared["cases"][0]["settings"]["request"]})
    captured = spike.call("prepare_em_resistor_cht_study", {"request": {
        "request": request, "study": prepared, "result": result}})
    print("Experimental result; production_qualified:", result.get("production_qualified"))
    print("Input digest:", result.get("input_digest_sha256"))
    print("Deposited power (W):", result.get("deposited_series_resistor_power_w"))
    if STUDY_FILE is not None:
        write_new(STUDY_FILE, captured)
        print("Study exported. Import it into Simulation studies and save the project.")
    if RESULT_FILE is not None:
        write_new(RESULT_FILE, result)
`;
}

/** Isolate the selected case: a multi-case study must never silently choose its first case. */
export function selectedEmResistorChtStudy(study: SimulationStudy, item: SimulationStudyCase, historical?: StudyRun): SimulationStudy {
  const matches = study.cases.filter(candidate => candidate.id === item.id);
  if (matches.length !== 1 || matches[0].type !== EM_RESISTOR_CHT_STUDY_TYPE) throw new Error("Select one saved AC/CHT case.");
  let selected = matches[0];
  if (historical) {
    const runs = selected.runs.filter(run => run.id === historical.id);
    if (runs.length !== 1) throw new Error("Select one retained historical capture.");
    const run = runs[0];
    selected = { ...selected, type: run.caseType, mode: run.mode, settings: run.settings, scenario: run.scenario,
      resultSnapshot: run.resultSnapshot, resultRef: run.resultRef };
  }
  return { ...study, cases: [structuredClone(selected)] };
}
