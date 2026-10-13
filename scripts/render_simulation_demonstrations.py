# SPDX-License-Identifier: Apache-2.0
"""Render self-contained HTML and PDF reports from executed SPIKE demo artifacts.

The renderer is intentionally strict: it refuses missing run evidence, incomplete
results, non-finite values, or production-qualified claims. It only summarizes
the JSON artifacts already written by the headless SPIKE worker.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "output" / "simulation-demonstrations-20261009"
SCENARIOS = ("single-board", "stacked-boards", "harness-stacks")
REQUIRED = (
    "scenario.json", "assembly.json", "designs.json", "source-provenance.json",
    "pi-request.json", "pi-result.json", "si-request.json", "si-result.json",
    "thermal-request.json", "thermal-result.json", "thermal-transient-request.json",
    "thermal-transient-result.json", "electrical-validation.json", "thermal-validation.json",
)
INK = colors.HexColor("#17243a")
BLUE = colors.HexColor("#215a9a")
CYAN = colors.HexColor("#159eaa")
ORANGE = colors.HexColor("#d87b26")
PALE = colors.HexColor("#eaf1f8")
MUTED = colors.HexColor("#5d6b7c")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fmt(value: Any, unit: str = "") -> str:
    if not finite(value):
        return str(value)
    av = abs(float(value))
    if av == 0:
        body = "0"
    elif av >= 1e5 or av < 1e-3:
        body = f"{value:.4e}"
    elif av >= 100:
        body = f"{value:.2f}"
    else:
        body = f"{value:.4g}"
    return body + (f" {unit}" if unit else "")


def clean_label(value: str, limit: int = 58) -> str:
    value = value.replace('node["', "").replace('element["', "").replace('\\"', "")
    value = value.replace('"]', "").replace('"', "").replace(",", " / ")
    return value if len(value) <= limit else value[: limit - 3] + "..."


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_run(folder: Path) -> dict[str, dict[str, Any]]:
    missing = [name for name in REQUIRED if not (folder / name).is_file()]
    if missing:
        raise FileNotFoundError(f"{folder.name}: missing run artifacts: {', '.join(missing)}")
    data = {name: read_json(folder / name) for name in REQUIRED}
    for name in ("pi-result.json", "si-result.json", "thermal-result.json", "thermal-transient-result.json"):
        result = data[name]
        if result.get("status") != "completed":
            raise ValueError(f"{folder.name}/{name}: expected completed status")
        if result.get("production_qualified") is True:
            raise ValueError(f"{folder.name}/{name}: demonstration must not claim production qualification")
    return data


def boards(assembly: dict[str, Any]) -> list[dict[str, Any]]:
    raw = assembly.get("boards")
    if raw is None and isinstance(assembly.get("assembly"), dict):
        raw = assembly["assembly"].get("boards")
    if not isinstance(raw, list) or not raw:
        raise ValueError("assembly.json has no board occurrences")
    return raw


def design_map(designs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw: Any = designs.get("designs", designs)
    if isinstance(raw, list):
        return {str(d.get("design_id", d.get("id", i))): d for i, d in enumerate(raw)}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    raise ValueError("designs.json has no design collection")


def board_bounds(board: dict[str, Any], designs: dict[str, dict[str, Any]]) -> tuple[float, float, float, float]:
    design = designs.get(str(board.get("design_id")), {})
    meta = design.get("metadata", {}) if isinstance(design, dict) else {}
    bounds = meta.get("board_bounds_mm") or design.get("board_bounds_mm") or board.get("board_bounds_mm")
    if isinstance(bounds, list) and len(bounds) == 4 and all(finite(v) for v in bounds):
        return float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3])
    return 0.0, 0.0, 60.0, 40.0


def transform(board: dict[str, Any]) -> list[float]:
    frame = board.get("frame", {})
    raw = frame.get("transform") if isinstance(frame, dict) else None
    if not isinstance(raw, list):
        raw = board.get("transform")
    if not isinstance(raw, list) or len(raw) != 16 or not all(finite(v) for v in raw):
        raise ValueError(f"board {board.get('id', '?')} has no finite 4x4 physical transform")
    return [float(v) for v in raw]


def figure_bytes(fig: Any) -> bytes:
    stream = io.BytesIO()
    fig.savefig(stream, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return stream.getvalue()


def assembly_figure(assembly: dict[str, Any], designs: dict[str, Any]) -> bytes:
    ds = design_map(designs)
    entries = []
    for index, board in enumerate(boards(assembly)):
        matrix = transform(board)
        bounds = board_bounds(board, ds)
        corners = []
        for local_x, local_y in ((bounds[0], bounds[1]), (bounds[2], bounds[1]),
                                 (bounds[2], bounds[3]), (bounds[0], bounds[3])):
            corners.append((matrix[0] * local_x + matrix[1] * local_y + matrix[3],
                            matrix[4] * local_x + matrix[5] * local_y + matrix[7]))
        entries.append((board, corners, matrix[11], index))
    fig, ax = plt.subplots(figsize=(9, 4.5))
    palette = ("#2774ae", "#18a999", "#e88536", "#7656a8", "#bd3f5a")
    centers = [(sum(point[0] for point in corners) / 4,
                sum(point[1] for point in corners) / 4) for _, corners, _, _ in entries]
    rounded = [(round(x, 4), round(y, 4)) for x, y in centers]
    for entry_index, (board, corners, z, index) in enumerate(entries):
        color = palette[index % len(palette)]
        ax.add_patch(Polygon(corners, closed=True, facecolor=color, edgecolor="#17243a", alpha=.58, linewidth=1.6))
        label = str(board.get("name") or board.get("id") or f"board {index + 1}")
        center_x, center_y = centers[entry_index]
        same_center = [i for i, value in enumerate(rounded) if value == rounded[entry_index]]
        slot = same_center.index(entry_index)
        offset_y = (slot - (len(same_center) - 1) / 2) * 28
        ax.annotate(f"{label} | z = {z:.2f} mm", xy=(center_x, center_y),
                    xytext=(0, offset_y), textcoords="offset points", ha="center", va="center",
                    fontsize=7.5, weight="bold",
                    bbox={"boxstyle": "round,pad=.25", "facecolor": "white", "alpha": .78, "edgecolor": color})
    ax.autoscale_view()
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("Assembly X (mm)")
    ax.set_ylabel("Assembly Y (mm)")
    ax.set_title("Physical board occurrences from assembly transforms")
    ax.grid(True, alpha=.22)
    return figure_bytes(fig)


def pi_data(result: dict[str, Any]) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    data = result.get("native_result", {}).get("data") or result.get("data", {})
    keys = ("node_voltage_v", "element_current_a", "element_power_w")
    output = []
    for key in keys:
        values = data.get(key, {})
        if not isinstance(values, dict) or not values:
            raise ValueError(f"PI result has no {key}")
        clean = {str(k): float(v) for k, v in values.items() if finite(v)}
        if not clean:
            raise ValueError(f"PI result {key} has no finite values")
        output.append(clean)
    return output[0], output[1], output[2]


def pi_figure(result: dict[str, Any]) -> bytes:
    volts, currents, powers = pi_data(result)
    groups = [("Node voltage (V)", volts), ("Element current (A)", currents), ("Element power (W)", powers)]
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.2))
    for ax, (title, values), color in zip(axes, groups, ("#2774ae", "#18a999", "#e88536")):
        rows = sorted(values.items(), key=lambda item: abs(item[1]), reverse=True)[:6]
        labels = [clean_label(k, 25) for k, _ in rows][::-1]
        vals = [v for _, v in rows][::-1]
        ax.barh(labels, vals, color=color, alpha=.82)
        ax.axvline(0, color="#17243a", linewidth=.7)
        ax.set_title(title, fontsize=10, weight="bold")
        ax.tick_params(labelsize=7)
        ax.grid(axis="x", alpha=.22)
    fig.suptitle("Returned PI operating point", fontsize=14, weight="bold")
    fig.tight_layout()
    return figure_bytes(fig)


def si_series(result: dict[str, Any]) -> tuple[list[float], list[tuple[str, list[float], list[float]]]]:
    data = result.get("native_result", {}).get("data") or result.get("data", {})
    freq = data.get("frequency_hz")
    values = data.get("node_voltage_v", {})
    if not isinstance(freq, list) or len(freq) < 2 or not all(finite(v) and v > 0 for v in freq):
        raise ValueError("SI result needs at least two positive finite frequency points")
    series = []
    for key, value in values.items():
        if not isinstance(value, dict):
            continue
        mag, phase = value.get("magnitude"), value.get("phase_deg")
        if isinstance(mag, list) and isinstance(phase, list) and len(mag) == len(freq) == len(phase):
            if all(finite(v) for v in mag + phase):
                series.append((str(key), [float(v) for v in mag], [float(v) for v in phase]))
    if not series:
        raise ValueError("SI result has no finite magnitude/phase node response")
    series.sort(key=lambda row: max(row[1]), reverse=True)
    return [float(v) for v in freq], series[:4]


def si_figure(result: dict[str, Any]) -> bytes:
    freq, series = si_series(result)
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 6.1), sharex=True)
    for name, mag, phase in series:
        label = clean_label(name, 42)
        axes[0].semilogx(freq, mag, marker="o", markersize=2.7, label=label)
        axes[1].semilogx(freq, phase, marker="o", markersize=2.7, label=label)
    axes[0].set_ylabel("Magnitude (V/V)")
    axes[1].set_ylabel("Phase (deg)")
    axes[1].set_xlabel("Frequency (Hz)")
    axes[0].set_title("Returned SI AC response")
    for ax in axes:
        ax.grid(True, which="both", alpha=.23)
    axes[0].legend(fontsize=7, loc="best")
    fig.tight_layout()
    return figure_bytes(fig)


def thermal_nodes(result: dict[str, Any]) -> list[tuple[str, float, float]]:
    rows = []
    ambient = result.get("ambient_temperature_c")
    for node in result.get("nodes", []):
        temp = node.get("temperature_c", node.get("steady_temperature_c"))
        if finite(temp):
            label = str(node.get("board_id") or node.get("id") or "thermal node")
            rows.append((label, float(temp), float(node.get("power_w", 0.0)) if finite(node.get("power_w")) else 0.0))
    if not rows:
        raise ValueError("thermal result has no finite node temperatures")
    if not finite(ambient):
        ambient = min(v for _, v, _ in rows)
    return rows


def thermal_table_rows(steady: dict[str, Any], validation: dict[str, Any]) -> list[list[str]]:
    final = validation.get("final_600s_temperatures_c", {})
    rows = []
    for name, temp, power in thermal_nodes(steady):
        final_temp = final.get(name) if isinstance(final, dict) else None
        if final_temp is None and isinstance(final, dict):
            for key, value in final.items():
                try:
                    decoded = json.loads(key)
                except (TypeError, json.JSONDecodeError):
                    decoded = None
                if isinstance(decoded, list) and decoded and decoded[0] == name:
                    final_temp = value
                    break
        rows.append([name, fmt(temp, "deg C"), fmt(final_temp, "deg C"), fmt(power, "W")])
    return rows


def transient_series(result: dict[str, Any]) -> list[tuple[str, list[float], list[float]]]:
    raw = result.get("transient", [])
    output: list[tuple[str, list[float], list[float]]] = []
    if isinstance(raw, list) and raw:
        if all(isinstance(row, dict) and finite(row.get("time_s")) for row in raw):
            node_names = sorted({str(k) for row in raw for k in (row.get("temperatures_c") or {}).keys()})
            for name in node_names:
                times, temps = [], []
                for row in raw:
                    value = (row.get("temperatures_c") or {}).get(name)
                    if finite(value):
                        times.append(float(row["time_s"])); temps.append(float(value))
                if times:
                    output.append((name, times, temps))
        else:
            grouped: dict[str, tuple[list[float], list[float]]] = {}
            for row in raw:
                if not isinstance(row, dict):
                    continue
                time = row.get("time_s")
                temp = row.get("temperature_c")
                if finite(time) and finite(temp):
                    key = str(row.get("board_id") or row.get("node_id") or row.get("id") or "node")
                    grouped.setdefault(key, ([], []))[0].append(float(time))
                    grouped[key][1].append(float(temp))
            output = [(k, v[0], v[1]) for k, v in grouped.items()]
    if not output:
        raise ValueError("transient thermal result has no finite time/temperature series")
    return output


def thermal_figure(steady: dict[str, Any], transient: dict[str, Any]) -> bytes:
    nodes = thermal_nodes(steady)
    series = transient_series(transient)
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.5))
    axes[0].bar([clean_label(v[0], 20) for v in nodes], [v[1] for v in nodes], color="#e88536", alpha=.85)
    axes[0].set_ylabel("Temperature (deg C)")
    axes[0].set_title("Steady node temperatures")
    axes[0].tick_params(axis="x", labelrotation=25, labelsize=8)
    axes[0].grid(axis="y", alpha=.22)
    for name, times, temps in series[:5]:
        axes[1].plot(times, temps, label=clean_label(name, 28))
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Temperature (deg C)")
    axes[1].set_title("Returned thermal transient")
    axes[1].grid(True, alpha=.22)
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    return figure_bytes(fig)


def validation_rows(value: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for key, item in value.items():
        if key in {"contract", "scenario_id", "model_status", "production_qualified",
                   "assumptions", "validation_limits", "inputs_sha256"}:
            continue
        if isinstance(item, dict) and isinstance(item.get("passed"), bool):
            status = "PASS" if item["passed"] else "FAIL"
            metrics = [(k, v) for k, v in item.items() if k not in {"passed", "reference"}]
            rows.append([key.replace("_", " ").upper(), status, str(item.get("reference", "checks passed"))])
            for metric, metric_value in metrics:
                detail = (", ".join(f"{k}={fmt(v)}" for k, v in metric_value.items())
                          if isinstance(metric_value, dict) else fmt(metric_value))
                rows.append([metric.replace("_", " "), "RECORDED", detail])
        elif isinstance(item, bool):
            rows.append([key.replace("_", " ").title(), "PASS" if item else "FAIL", str(item).lower()])
        elif isinstance(item, dict) and any(k in item for k in ("status", "passed", "valid", "value", "tolerance")):
            status = item.get("status", item.get("passed", item.get("valid", "recorded")))
            detail = ", ".join(f"{k}={fmt(v)}" for k, v in item.items() if k not in {"status", "passed", "valid"})
            rows.append([key.replace("_", " ").title(), str(status).upper(), detail or "-"])
        elif key in {"status", "valid", "passed"}:
            rows.append(["Overall", str(item).upper(), "-"])
    if not rows:
        rows.append(["Recorded validation", str(value.get("status", "see artifact")).upper(), "No normalized checks exposed"])
    return rows


def issues(data: dict[str, dict[str, Any]]) -> list[str]:
    result = []
    for name in ("pi-result.json", "si-result.json", "thermal-result.json", "thermal-transient-result.json"):
        for issue in data[name].get("issues", []):
            if isinstance(issue, dict):
                result.append(f"{name[:-5]} - {issue.get('code', 'issue')}: {issue.get('message', '')}")
    fixed = [
        "Headless SPIKE worker execution; this report does not establish GUI workflow verification.",
        "Electrical values come from a supplied reduced linear circuit model; no PCB full-wave field extraction was performed.",
        "Thermal values come from a supplied lumped RC network; no FEA, CFD, calibrated material fit, or hardware correlation was performed.",
        "Results are engineering demonstrations and are not production or hardware qualification evidence.",
    ]
    thermal_notes = data.get("thermal-validation.json", {}).get("assumptions", {}).get("notes", [])
    if isinstance(thermal_notes, list):
        result.extend(str(value) for value in thermal_notes)
    return fixed + result


def scenario_title(scenario: dict[str, Any], folder: Path) -> str:
    return str(scenario.get("title") or scenario.get("name") or folder.name.replace("-", " ").title())


def source_rows(provenance: dict[str, Any]) -> list[list[str]]:
    rows = []
    for key, value in provenance.items():
        if isinstance(value, dict):
            label = value.get("product") or value.get("name") or key
            digest = value.get("sha256") or value.get("source_sha256") or value.get("archive_sha256") or "recorded in JSON"
            origin = value.get("url") or value.get("path") or value.get("source") or "local run input"
            rows.append([str(label), str(origin), str(digest)])
    if not rows:
        rows.append(["Run inputs", "See source-provenance.json", sha256_placeholder(provenance)])
    return rows


def assumption_items(scenario: dict[str, Any]) -> list[str]:
    values = scenario.get("assumptions", [])
    return [str(value) for value in values] if isinstance(values, list) else []


def circuit_setup_rows(scenario: dict[str, Any]) -> list[list[str]]:
    rows = []
    for board in scenario.get("board_elements", []):
        board_id = str(board.get("board_id", "board"))
        for element in board.get("elements", []):
            properties = []
            for key in ("dc_value", "resistance_ohm", "inductance_h", "capacitance_f", "ac_magnitude"):
                if key in element:
                    properties.append(f"{key}={fmt(element[key])}")
            rows.append([board_id, str(element.get("id", "element")), str(element.get("type", "-")), ", ".join(properties) or "-"])
    return rows or [["-", "See request JSON", "-", "No scenario summary"]]


def sha256_placeholder(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def img_uri(raw: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def html_table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    head = "".join(f"<th>{esc(v)}</th>" for v in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def html_report(folder: Path, data: dict[str, dict[str, Any]], figures: dict[str, bytes]) -> str:
    scenario = data["scenario.json"]
    title = scenario_title(scenario, folder)
    assembly = data["assembly.json"]
    b_rows = []
    for board in boards(assembly):
        m = transform(board)
        b_rows.append([board.get("id", "-"), board.get("design_id", "-"), f"({m[3]:.3f}, {m[7]:.3f}, {m[11]:.3f})"])
    volts, currents, powers = pi_data(data["pi-result.json"])
    pi_rows = [[clean_label(k), fmt(v, "V")] for k, v in sorted(volts.items(), key=lambda x: abs(x[1]), reverse=True)[:8]]
    pi_rows += [[clean_label(k), fmt(v, "A")] for k, v in sorted(currents.items(), key=lambda x: abs(x[1]), reverse=True)[:6]]
    pi_rows += [[clean_label(k), fmt(v, "W")] for k, v in sorted(powers.items(), key=lambda x: abs(x[1]), reverse=True)[:6]]
    freq, series = si_series(data["si-result.json"])
    si_rows = [[clean_label(n), fmt(m[0]), fmt(m[-1]), fmt(p[-1], "deg")] for n, m, p in series]
    t_rows = thermal_table_rows(data["thermal-result.json"], data["thermal-validation.json"])
    all_validation = validation_rows(data["electrical-validation.json"]) + validation_rows(data["thermal-validation.json"])
    digest_rows = [[name, sha256(folder / name)] for name in REQUIRED]
    issue_html = "".join(f"<li>{esc(v)}</li>" for v in issues(data))
    assumption_html = "".join(f"<li>{esc(v)}</li>" for v in assumption_items(scenario))
    board_count = len(boards(assembly))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} - SPIKE simulation report</title>
<style>:root{{--ink:#17243a;--blue:#215a9a;--cyan:#159eaa;--orange:#d87b26;--pale:#eaf1f8;--muted:#5d6b7c}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.55 Segoe UI,Arial,sans-serif;color:var(--ink);background:#f3f6f9}}
main{{max-width:1080px;margin:auto;background:white;box-shadow:0 0 30px #ccd4dd;padding:0 56px 60px}}
header{{margin:0 -56px 34px;padding:64px 56px 52px;background:linear-gradient(135deg,#142742,#215a9a);color:white}}
.eyebrow{{text-transform:uppercase;letter-spacing:.14em;color:#9be7ed;font-weight:700}}h1{{font-size:40px;line-height:1.1;margin:.25em 0}}
h2{{margin-top:2.2em;border-bottom:3px solid var(--cyan);padding-bottom:.3em}}h3{{color:var(--blue)}}.lede{{font-size:19px;max-width:800px}}
.status{{display:inline-block;padding:5px 10px;border-radius:20px;background:#f7d9bb;color:#6e3510;font-weight:700}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.card{{padding:18px;background:var(--pale);border-radius:8px}}.metric{{font-size:27px;font-weight:700;color:var(--blue)}}
nav ol{{columns:2}}figure{{margin:24px 0}}figure img{{width:100%;height:auto;border:1px solid #d5dde6;border-radius:6px}}figcaption{{color:var(--muted);font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:14px 0 24px}}th{{background:var(--ink);color:white;text-align:left}}th,td{{padding:8px 10px;border:1px solid #d7dee7;vertical-align:top}}tr:nth-child(even) td{{background:#f5f8fb}}
.warning{{border-left:5px solid var(--orange);background:#fff4e8;padding:16px 18px}}code{{font-family:Consolas,monospace}}.hashes td:last-child{{font:11px Consolas,monospace;overflow-wrap:anywhere}}
@media(max-width:700px){{main{{padding:0 20px 40px}}header{{margin:0 -20px 24px;padding:40px 20px}}.grid{{grid-template-columns:1fr}}nav ol{{columns:1}}}}
@media print{{body{{background:white}}main{{box-shadow:none;max-width:none}}header{{print-color-adjust:exact}}h2{{break-before:page}}figure,table{{break-inside:avoid}}}}</style></head><body><main>
<header><div class="eyebrow">SPIKE engineering demonstration</div><h1>{esc(title)}</h1><p class="lede">Executed PI, SI, steady thermal, and transient thermal results for a {board_count}-board assembly.</p><span class="status">Experimental / approximate - not production qualified</span></header>
<nav><h2>Contents</h2><ol><li><a href="#scope">Scope and setup</a></li><li><a href="#assembly">Physical assembly</a></li><li><a href="#pi">Power integrity</a></li><li><a href="#si">Signal integrity</a></li><li><a href="#thermal">Thermal</a></li><li><a href="#validation">Validation evidence</a></li><li><a href="#limits">Limitations and conclusion</a></li><li><a href="#reproduce">Reproduction</a></li></ol></nav>
<section id="scope"><h2>1. Scope and setup</h2><p>{esc(scenario.get('description', scenario.get('summary', 'Headless SPIKE worker simulation demonstration.')))}</p>
<div class="grid"><div class="card"><div class="metric">{board_count}</div>board occurrences</div><div class="card"><div class="metric">{len(freq)}</div>SI frequency points</div><div class="card"><div class="metric">{len(transient_series(data['thermal-transient-result.json']))}</div>thermal traces</div></div>
<h3>Supplied circuit setup</h3>{html_table(('Board','Element','Type','Supplied value'), circuit_setup_rows(scenario))}<h3>Model assumptions</h3><ul>{assumption_html}</ul>
<h3>Source provenance</h3>{html_table(('Source','Origin','SHA-256 / evidence'), source_rows(data['source-provenance.json']))}</section>
<section id="assembly"><h2>2. Physical assembly</h2><p>The diagram and coordinates are derived from the 4x4 transforms in <code>assembly.json</code>.</p><figure><img src="{img_uri(figures['assembly'])}" alt="Board assembly diagram"><figcaption>Top view; labels include the transform Z coordinate. Board extents come from retained design metadata when available.</figcaption></figure>{html_table(('Occurrence','Design','Translation xyz (mm)'), b_rows)}</section>
<section id="pi"><h2>3. Power integrity operating point</h2><p>The native linear MNA result reports voltages, currents, and element power for the supplied reduced circuit.</p><figure><img src="{img_uri(figures['pi'])}" alt="PI operating point charts"></figure>{html_table(('Returned quantity','Value'), pi_rows)}</section>
<section id="si"><h2>4. Signal integrity frequency response</h2><p>Magnitude and phase are plotted directly from returned AC node responses over {fmt(freq[0], 'Hz')} to {fmt(freq[-1], 'Hz')}.</p><figure><img src="{img_uri(figures['si'])}" alt="SI magnitude and phase plots"></figure>{html_table(('Node response','Magnitude start','Magnitude stop','Phase stop'), si_rows)}</section>
<section id="thermal"><h2>5. Thermal response</h2><p>Steady and transient results use the supplied reduced board RC network and explicit thermal connections.</p><figure><img src="{img_uri(figures['thermal'])}" alt="Steady and transient thermal plots"></figure>{html_table(('Thermal node','Steady temperature','Final at 600 s','Power'), t_rows)}</section>
<section id="validation"><h2>6. Recorded validation</h2><p>These are the checks saved beside the run. A completed solver call does not by itself establish physical accuracy.</p>{html_table(('Check','Status','Returned detail'), all_validation)}</section>
<section id="limits"><h2>7. Limitations and conclusion</h2><div class="warning"><ul>{issue_html}</ul></div><h3>Conclusion</h3><p>The headless run completed and produced internally checked reduced-model responses for this configured scenario. The artifacts support workflow demonstration and engineering precheck use within their stated contracts. They do not establish extracted board-field accuracy, enclosure airflow, component package temperatures, standards compliance, or hardware qualification.</p></section>
<section id="reproduce"><h2>8. Reproduction and artifact identity</h2><p>Use the repository <code>.venv</code> with its locked runtime dependencies. From PowerShell at the repository root:</p><pre><code>$env:OMP_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
./.venv/Scripts/python.exe scripts/run_simulation_demonstrations.py
foreach ($scenario in "single-board", "stacked-boards", "harness-stacks") {{
  ./.venv/Scripts/python.exe scripts/run_demo_thermal.py "output/simulation-demonstrations-20261009/$scenario"
}}
./.venv/Scripts/python.exe scripts/render_simulation_demonstrations.py --root output/simulation-demonstrations-20261009</code></pre><ol><li>Confirm every solver result has completed status.</li><li>Confirm <code>electrical-validation.json</code> and <code>thermal-validation.json</code> report passed checks.</li><li>Compare the hashes below when reviewing a retained report.</li></ol><p>The renderer reads existing artifacts and does not rerun or alter simulations.</p>{html_table(('Artifact','SHA-256'), digest_rows).replace('<table>', '<table class="hashes">', 1)}</section>
</main></body></html>"""


class Rule(Flowable):
    def __init__(self, width: float, color: colors.Color = CYAN) -> None:
        super().__init__(); self.width = width; self.color = color; self.height = 5
    def draw(self) -> None:
        self.canv.setStrokeColor(self.color); self.canv.setLineWidth(2); self.canv.line(0, 2, self.width, 2)


def pdf_report(folder: Path, data: dict[str, dict[str, Any]], figures: dict[str, bytes]) -> None:
    scenario = data["scenario.json"]
    title = scenario_title(scenario, folder)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=29, leading=33, textColor=colors.white, alignment=TA_LEFT, spaceAfter=14))
    styles.add(ParagraphStyle(name="CoverSub", parent=styles["BodyText"], fontSize=13, leading=18, textColor=colors.HexColor("#dcecff"), spaceAfter=9))
    styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=BLUE, spaceBefore=10, spaceAfter=7))
    styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=INK, spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontSize=9.3, leading=13, textColor=INK, spaceAfter=7))
    styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontSize=7.4, leading=9.3, textColor=MUTED, spaceAfter=4))
    styles.add(ParagraphStyle(name="Centerx", parent=styles["Bodyx"], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="TableHead", parent=styles["Smallx"], fontName="Helvetica-Bold", textColor=colors.white))
    doc = SimpleDocTemplate(str(folder / "report.pdf"), pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=18*mm, bottomMargin=17*mm, title=title, author="SPIKE")
    story: list[Any] = []

    def p(text: Any, style: str = "Bodyx") -> Paragraph:
        return Paragraph(html.escape(str(text)).replace("\n", "<br/>"), styles[style])

    def h(text: str) -> list[Any]:
        return [Paragraph(text, styles["H1x"]), Rule(178*mm), Spacer(1, 4*mm)]

    def table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None, small: bool = False) -> Table:
        payload = [[Paragraph(html.escape(str(v)), styles["TableHead"]) for v in headers]]
        payload += [[Paragraph(html.escape(str(v)), styles["Smallx"] if small else styles["Bodyx"]) for v in row] for row in rows]
        t = Table(payload, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),INK),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#b8c5d2")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f3f7fa")]),("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        return t

    def image(raw: bytes, width: float = 175*mm) -> Image:
        stream = io.BytesIO(raw)
        img = Image(stream)
        scale = min(width / img.imageWidth, 112*mm / img.imageHeight)
        img.drawWidth = img.imageWidth * scale; img.drawHeight = img.imageHeight * scale
        return img

    def on_page(canvas: Any, document: Any) -> None:
        canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#c8d3df")); canvas.line(16*mm, 14*mm, 194*mm, 14*mm)
        canvas.setFillColor(MUTED); canvas.setFont("Helvetica", 7.5)
        canvas.drawString(16*mm, 9*mm, f"SPIKE | {folder.name}")
        canvas.drawRightString(194*mm, 9*mm, f"Page {document.page}"); canvas.restoreState()

    # Cover
    cover = Table([[Paragraph("SPIKE", ParagraphStyle(name="Brand", fontName="Helvetica-Bold", fontSize=17, textColor=colors.HexColor("#91e4eb"))), ""], [Paragraph(title, styles["CoverTitle"]), ""], [Paragraph("PI, SI, steady thermal, and transient thermal report", styles["CoverSub"]), ""], [Paragraph("EXPERIMENTAL / APPROXIMATE - NOT PRODUCTION QUALIFIED", ParagraphStyle(name="Badge", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#ffd6ac"))), ""]], colWidths=[150*mm, 28*mm], rowHeights=[18*mm, 58*mm, 19*mm, 24*mm])
    cover.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),INK),("SPAN",(0,0),(1,0)),("SPAN",(0,1),(1,1)),("SPAN",(0,2),(1,2)),("SPAN",(0,3),(1,3)),("LEFTPADDING",(0,0),(-1,-1),12*mm),("RIGHTPADDING",(0,0),(-1,-1),12*mm),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story += [Spacer(1, 22*mm), cover, Spacer(1, 13*mm), p(f"Scenario: {title}"), p("Generated only from the adjacent executed JSON artifacts. Headless SPIKE worker run; GUI behavior was not verified.", "Smallx"), PageBreak()]

    story += h("Contents")
    toc = [[str(i), name] for i, name in enumerate(("Scope, setup, and provenance", "Physical assembly", "Power integrity", "Signal integrity", "Thermal response", "Recorded validation", "Limitations and conclusion", "Reproduction and artifact identity"), 1)]
    story += [table(["Section", "Subject"], toc, [22*mm, 150*mm]), Spacer(1, 7*mm), p("Each technical section reports values returned by the run. Capability boundaries and solver issues are preserved."), PageBreak()]

    story += h("1. Scope, setup, and provenance")
    setup_rows = circuit_setup_rows(scenario)
    assumption_text = "<br/>".join(f"- {html.escape(value)}" for value in assumption_items(scenario))
    story += [p(scenario.get("description", scenario.get("summary", "Headless SPIKE simulation demonstration."))), p(f"Assembly occurrences: {len(boards(data['assembly.json']))}. Electrical result status: {data['pi-result.json'].get('status')}. Thermal result status: {data['thermal-result.json'].get('status')}."), Paragraph("Supplied circuit setup", styles["H2x"]), table(["Board","Element","Type","Supplied value"], setup_rows, [37*mm,47*mm,35*mm,59*mm], True), Paragraph("Model assumptions", styles["H2x"]), Paragraph(assumption_text or "See request artifacts.", styles["Smallx"]), Paragraph("Source provenance", styles["H2x"]), table(["Source", "Origin", "SHA-256 / evidence"], source_rows(data["source-provenance.json"]), [43*mm, 66*mm, 69*mm], True), PageBreak()]

    b_rows=[]
    for board in boards(data["assembly.json"]):
        m=transform(board); b_rows.append([board.get("id","-"),board.get("design_id","-"),f"{m[3]:.3f}, {m[7]:.3f}, {m[11]:.3f}"])
    story += h("2. Physical assembly")
    story += [p("The diagram is derived from the board occurrence transforms saved in assembly.json. It is evidence of placement data, not a mechanical clearance or enclosure check."), image(figures["assembly"]), Spacer(1,3*mm), table(["Occurrence","Design","Translation xyz (mm)"],b_rows,[45*mm,80*mm,53*mm],True), PageBreak()]

    volts,currents,powers=pi_data(data["pi-result.json"])
    pi_rows=[["Voltage",clean_label(k),fmt(v,"V")] for k,v in sorted(volts.items(),key=lambda x:abs(x[1]),reverse=True)[:6]]+[["Current",clean_label(k),fmt(v,"A")] for k,v in sorted(currents.items(),key=lambda x:abs(x[1]),reverse=True)[:4]]+[["Power",clean_label(k),fmt(v,"W")] for k,v in sorted(powers.items(),key=lambda x:abs(x[1]),reverse=True)[:4]]
    pi_diag=data["pi-result.json"].get("native_result",{}).get("diagnostics") or data["pi-result.json"].get("diagnostics",{})
    story += h("3. PI results")
    story += [image(figures["pi"]), Paragraph("Selected returned values",styles["H2x"]), table(["Kind","Quantity","Value"],pi_rows,[25*mm,115*mm,38*mm],True), p(f"Native modified nodal analysis for the supplied reduced circuit. Relative residual: {fmt(pi_diag.get('relative_residual_max'))}; points: {fmt(pi_diag.get('points'))}.","Smallx"), PageBreak()]

    freq,series=si_series(data["si-result.json"])
    si_rows=[[clean_label(n),fmt(m[0]),fmt(m[-1]),fmt(p[-1],"deg")] for n,m,p in series]
    story += h("4. SI frequency response")
    story += [image(figures["si"]), table(["Node response","Magnitude start","Magnitude stop","Phase stop"],si_rows,[82*mm,32*mm,32*mm,32*mm],True), p(f"Returned AC magnitude and phase from {fmt(freq[0],'Hz')} through {fmt(freq[-1],'Hz')} at {len(freq)} points. Curves are circuit-node transfer responses; they are not S-parameters, an eye diagram, or a field-extracted channel model.","Smallx"), PageBreak()]

    t_rows=thermal_table_rows(data["thermal-result.json"],data["thermal-validation.json"])
    ts=transient_series(data["thermal-transient-result.json"])
    thermal_summary=data["thermal-result.json"].get("summary",{})
    story += h("5. Thermal response")
    thermal_checks=data["thermal-validation.json"].get("validation",{})
    energy_residual=thermal_summary.get("energy_balance_residual_w",thermal_checks.get("independent_steady_energy_balance_residual_w"))
    node_residual=thermal_summary.get("max_node_residual_w",thermal_checks.get("independent_steady_max_node_residual_w"))
    story += [p("Steady and transient values from the supplied lumped thermal RC network."), image(figures["thermal"]), table(["Thermal node","Steady","Final at 600 s","Power"],t_rows,[72*mm,37*mm,40*mm,29*mm]), p(f"Returned transient traces: {len(ts)}. Steady energy-balance residual: {fmt(energy_residual,'W')}. Maximum node residual: {fmt(node_residual,'W')}.","Smallx"), PageBreak()]

    validation=validation_rows(data["electrical-validation.json"])+validation_rows(data["thermal-validation.json"])
    story += h("6. Recorded validation")
    story += [p("The following entries are read from the validation artifacts produced for this exact run."), table(["Check","Status","Returned detail"],validation,[60*mm,32*mm,86*mm],True), p("Validation here establishes the implemented numerical and contract checks only. It does not provide measurement correlation or release qualification."), PageBreak()]

    story += h("7. Limitations and conclusion")
    story.append(Paragraph("Capability boundary", styles["H2x"]))
    story.extend(p("- " + value, "Smallx") for value in issues(data))
    story += [Spacer(1,3*mm),Paragraph("Conclusion",styles["H2x"]),p("The headless run completed and produced internally checked reduced-model responses for the configured scenario. The evidence supports workflow demonstration and engineering precheck use within the stated contracts. It does not establish extracted field accuracy, enclosure airflow, standards compliance, or hardware qualification."),PageBreak()]

    digest_rows=[[name,sha256(folder/name)] for name in REQUIRED]
    story += h("8. Reproduction and artifact identity")
    reproduction = ("Use the repository .venv with its locked runtime dependencies. From PowerShell at the repository root:\n"
                    "$env:OMP_NUM_THREADS = \"1\"\n"
                    "$env:OPENBLAS_NUM_THREADS = \"1\"\n"
                    ".\\.venv\\Scripts\\python.exe scripts\\run_simulation_demonstrations.py\n"
                    "foreach ($scenario in \"single-board\", \"stacked-boards\", \"harness-stacks\") {\n"
                    "  .\\.venv\\Scripts\\python.exe scripts\\run_demo_thermal.py \"output\\simulation-demonstrations-20261009\\$scenario\"\n"
                    "}\n"
                    ".\\.venv\\Scripts\\python.exe scripts\\render_simulation_demonstrations.py --root output\\simulation-demonstrations-20261009\n\n"
                    "Then confirm completed solver status, passed electrical and thermal validation, and the hashes below.")
    story += [p(reproduction),Paragraph("Artifact SHA-256",styles["H2x"]),table(["Artifact","SHA-256"],digest_rows,[58*mm,120*mm],True)]
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


def render(folder: Path) -> None:
    data = require_run(folder)
    figures = {
        "assembly": assembly_figure(data["assembly.json"], data["designs.json"]),
        "pi": pi_figure(data["pi-result.json"]),
        "si": si_figure(data["si-result.json"]),
        "thermal": thermal_figure(data["thermal-result.json"], data["thermal-transient-result.json"]),
    }
    (folder / "report.html").write_text(html_report(folder, data, figures), encoding="utf-8")
    pdf_report(folder, data, figures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--scenario", choices=SCENARIOS, action="append")
    args = parser.parse_args()
    selected = args.scenario or list(SCENARIOS)
    for name in selected:
        folder = args.root.resolve() / name
        render(folder)
        print(f"rendered {folder / 'report.html'}")
        print(f"rendered {folder / 'report.pdf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
