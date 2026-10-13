# SPDX-License-Identifier: Apache-2.0
"""Build the original board package and run its host-compiled C++ firmware demo.

Run from the repository root in a C++ developer environment:
python -m examples.compiled_board.build_and_run --engine PATH --output NEW_DIR
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from python.spikes.board_library import AnalogInput, BoardOutput, BoardLimits, compile_board_library
from python.spikes.netlist import parse_netlist


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args(argv)
    fixture = Path(__file__).resolve().parent
    root = args.output.resolve()
    if root.exists():
        raise FileExistsError("Demo output must be a new directory")
    config = json.loads((fixture / "pins.json").read_text())
    project = parse_netlist((fixture / "rc_board.cir").read_text(), source_name=str(fixture / "rc_board.cir"))
    engine = args.engine.resolve(strict=True)
    manifest = compile_board_library(project, root / "rc_board", name=config["name"],
        inputs=[AnalogInput(**p) for p in config["inputs"]],
        outputs=[BoardOutput(**p) for p in config["outputs"]],
        limits=BoardLimits(**config["limits"]), engine_library=engine, compiler=args.compiler)
    package = manifest.parent
    compiler = str(args.compiler or shutil.which("cl.exe" if os.name == "nt" else "c++"))
    executable = root / ("firmware.exe" if os.name == "nt" else "firmware")
    if os.name == "nt":
        command = [compiler, "/nologo", "/std:c++20", "/EHsc", "/MD", f"/I{package}",
                   str(fixture / "firmware.cpp"), str(package / "rc_board.lib"), f"/Fe:{executable}"]
    else:
        suffix = ".dylib" if sys.platform == "darwin" else ".so"
        command = [compiler, "-std=c++20", f"-I{package}", str(fixture / "firmware.cpp"),
                   str(package / ("rc_board"+suffix)), f"-Wl,-rpath,{package}", "-o", str(executable)]
    with (root / "firmware-build.log").open("wb") as log:
        subprocess.run(command, cwd=root, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    env = dict(os.environ)
    env["PATH"] = str(package) + os.pathsep + str(engine.parent) + os.pathsep + env.get("PATH", "")
    with (root / "firmware-output.txt").open("wb") as log:
        subprocess.run([str(executable)], cwd=root, env=env, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=30)
    print((root / "firmware-output.txt").read_text().strip())
    print(f"Board manifest: {manifest}")
    print(f"Firmware executable: {executable}")


if __name__ == "__main__":
    main()
