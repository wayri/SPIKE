"""Real compiler invocations and digital timing import for the Studio IDE."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def find_tool(name):
    found = shutil.which(name)
    if found: return found
    if name=="cl" and os.name=="nt":
        root=Path(os.environ.get("ProgramFiles","C:/Program Files"))/"Microsoft Visual Studio"
        candidates=sorted(root.glob("*/*/VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe"),reverse=True)
        if candidates:return str(candidates[0])
    for parent in Path(__file__).resolve().parents:
        for root in (parent / "tools/hdl/oss-cad-suite/oss-cad-suite/bin", parent / "tools/hdl/iverilog-standalone/bin"):
            candidate = root / (name + (".exe" if os.name == "nt" else ""))
            if candidate.is_file(): return str(candidate)
    return None


def analyze(source, language, mode="check", top="top"):
    if mode not in ("check", "synthesize", "simulate"):raise ValueError("Unknown build mode")
    if mode=="simulate" and language!="Verilog":raise ValueError("Digital simulation currently requires a Verilog testbench")
    if len(source.encode()) > 2 * 1024 * 1024: raise ValueError("Source exceeds 2 MiB")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", top): raise ValueError("Invalid module identifier")
    tool = "yosys" if mode == "synthesize" and language == "Verilog" else "iverilog" if language == "Verilog" else "clang++" if language == "C++" else "clang"
    if mode == "synthesize" and language != "Verilog": raise ValueError("Synthesis currently supports Verilog; C/C++ high-level synthesis requires a separate backend")
    executable = find_tool(tool)
    if not executable and tool in ("clang", "clang++"):
        executable=find_tool("cl")
        if executable:tool="cl"
    if not executable: raise ValueError(f"{tool} is not installed/configured")
    with tempfile.TemporaryDirectory(prefix="spikes-ide-") as directory:
        work = Path(directory)
        file = work / ("design.v" if language == "Verilog" else "design.cpp" if language == "C++" else "design.c")
        file.write_text(source, encoding="utf-8")
        if tool == "yosys":
            argv = [executable, "-p", f"read_verilog design.v; hierarchy -check -top {top}; synth -top {top}; stat; write_json netlist.json"]
        elif tool == "iverilog": argv = [executable, "-g2012", "-Wall", "-s", top, "-o", "design.vvp", file.name]
        elif tool=="cl":argv=[executable,"/nologo","/Zs","/W4","/TP" if language=="C++" else "/TC","/std:c++20" if language=="C++" else "/std:c17",file.name]
        else: argv = [executable, "-fsyntax-only", "-Wall", "-Wextra", "-std=c++20" if language == "C++" else "-std=c17", file.name]
        environment = dict(os.environ)
        bin_dir=Path(executable).parent
        environment["PATH"] = os.pathsep.join((str(bin_dir),str(bin_dir.parent/"lib"),environment.get("PATH", "")))
        if tool=="cl":
            include=[str(bin_dir.parents[2]/"include")]
            sdk=Path(os.environ.get("ProgramFiles(x86)","C:/Program Files (x86)"))/"Windows Kits/10/Include"
            versions=sorted(sdk.glob("10.*"),reverse=True)
            if versions:include.extend(str(versions[0]/name) for name in ("ucrt","shared","um"))
            environment["INCLUDE"]=os.pathsep.join(include+[environment.get("INCLUDE","")])
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(argv, cwd=work, env=environment, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try: process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
                raise ValueError("Build exceeded 45 seconds")
            log.seek(0)
            output = log.read(2 * 1024 * 1024 + 1)
            if len(output) > 2 * 1024 * 1024: raise ValueError("Build log exceeded 2 MiB")
        report = {"tool": executable, "argv": argv, "exit_code": process.returncode, "output": output.decode(errors="replace"), "mode": mode}
        report["output"]=report["output"].replace("\r\r\n","\n").replace("\r\n","\n")
        if mode=="simulate" and process.returncode==0:
            runtime=find_tool("vvp")
            if not runtime:raise ValueError("vvp is not installed/configured")
            with tempfile.TemporaryFile() as simulation_log:
                process=subprocess.Popen([runtime,"design.vvp"],cwd=work,env=environment,stdout=simulation_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait();raise ValueError("Digital simulation exceeded 15 seconds; use a bounded testbench")
                simulation_log.seek(0);output=simulation_log.read(2*1024*1024+1)
                if len(output)>2*1024*1024:raise ValueError("Digital simulation log exceeded 2 MiB")
            report["exit_code"]=process.returncode;report["output"]+=output.decode(errors="replace")
            wavefiles=list(work.glob("*.vcd"))
            if wavefiles:
                if wavefiles[0].stat().st_size>16*1024*1024:raise ValueError("VCD exceeded 16 MiB")
                report["vcd_source"]=wavefiles[0].read_text()
                report["timing"]=read_vcd(report["vcd_source"])
        if (work / "netlist.json").exists() and process.returncode == 0:
            report["netlist"] = json.loads((work / "netlist.json").read_text())
        return report


def read_vcd(text):
    """Parse declared scalar/vector transitions, X/Z, hierarchy and timescale."""
    if len(text) > 16 * 1024 * 1024: raise ValueError("VCD exceeds 16 MiB")
    scale = re.search(r"\$timescale\s+(\d+)\s*(s|ms|us|ns|ps|fs)\s+\$end", text)
    if not scale: raise ValueError("VCD needs an explicit timescale")
    tick = int(scale[1]) * {"s": 1, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}[scale[2]]
    tokens = text.split()
    scope, codes, signals = [], {}, {}
    index, time, last = 0, 0.0, 0.0
    while index < len(tokens):
        token = tokens[index]; index += 1
        if token == "$scope":
            scope.append(tokens[index+1])
        elif token == "$upscope":
            if scope: scope.pop()
        elif token == "$var":
            kind, width, code, name = tokens[index:index+4]
            if kind == "real": raise ValueError("Real-valued VCD variables are not supported by the digital timing viewer")
            full = ".".join(scope + [name])
            codes.setdefault(code, []).append(full)
            signals[full] = {"width": int(width), "transitions": []}
        elif token.startswith("#"):
            time = int(token[1:]) * tick
            if time < last: raise ValueError("VCD timestamps decreased")
            last = time
        elif token and token[0].lower() in "01xz" and not token.startswith("$"):
            value, code = token[0].lower(), token[1:]
            for full in codes.get(code, []): signals[full]["transitions"].append((time, value))
        elif token and token[0].lower() == "b":
            if index < len(tokens):
                value, code = token[1:].lower(), tokens[index]; index += 1
                for full in codes.get(code, []): signals[full]["transitions"].append((time, value))
        if token.startswith("$") and token not in ("$dumpvars", "$end"):
            while index < len(tokens) and tokens[index] != "$end": index += 1
            index += 1
    if not signals: raise ValueError("No digital variables in VCD")
    return {"timescale_s": tick, "end_time_s": last, "signals": signals}
