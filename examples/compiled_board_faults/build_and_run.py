# SPDX-License-Identifier: Apache-2.0
"""Build and run the actual C++ and Python compiled-board fault demonstrations."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from python.spikes.board_library import AnalogInput, BoardLimits, BoardOutput, FaultBinding, compile_board_library
from python.spikes.board_library_client import BoardLibrary
from python.spikes.fault_injection import FaultSite, apply_fault
from python.spikes.fault_campaign import FaultCampaign, FaultEvent
from python.spikes.environment_faults import Exposure, ParameterResponse
from python.spikes.native_abi import load_native_library
from python.spikes.native_runner import _populate
from python.spikes.netlist import parse_netlist


def load_fixture():
    here = Path(__file__).resolve().parent
    config = json.loads((here / "board.json").read_text(encoding="utf-8"))
    project = parse_netlist((here / "fault_board.cir").read_text(encoding="utf-8"),
                            source_name=str(here / "fault_board.cir"))
    faults = [FaultBinding(FaultSite(**item["site"]), item.get("positive_node"), item.get("negative_node"))
              for item in config["faults"]]
    return here, config, project, faults


def native_value(engine: Path, project, faults, fault: str | None, value: float | None) -> float:
    library = load_native_library(engine)
    with library.circuit() as circuit:
        _populate(circuit, project)
        for binding in faults:
            if binding.positive_node is not None:
                circuit.add_resistor(binding.site.element_id, binding.positive_node,
                                     binding.negative_node, binding.site.healthy_value)
        with circuit.transient_session() as session:
            if fault is not None:
                site = next(binding.site for binding in faults if binding.site.name == fault)
                apply_fault(session, site, value)
            if not session.step(1e-6):
                raise RuntimeError(session.message)
            return session.node_voltage("drain")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args(argv)
    here, config, project, faults = load_fixture()
    root = args.output.resolve()
    if root.exists():
        raise FileExistsError("Demo output must be a new directory")
    engine = args.engine.resolve(strict=True)
    manifest = compile_board_library(project, root / "fault_board", name=config["name"],
        inputs=[AnalogInput(**p) for p in config["inputs"]],
        outputs=[BoardOutput(**p) for p in config["outputs"]],
        limits=BoardLimits(**config["limits"]), engine_library=engine,
        compiler=args.compiler, faults=faults)
    package = manifest.parent
    compiler = str(args.compiler or shutil.which("cl.exe" if os.name == "nt" else "c++"))
    executable = root / ("fault_firmware.exe" if os.name == "nt" else "fault_firmware")
    if os.name == "nt":
        command = [compiler, "/nologo", "/std:c++20", "/EHsc", "/MD", f"/I{package}",
                   str(here / "fault_firmware.cpp"), str(package / "fault_board.lib"), f"/Fe:{executable}"]
    else:
        suffix = ".dylib" if sys.platform == "darwin" else ".so"
        command = [compiler, "-std=c++20", f"-I{package}", str(here / "fault_firmware.cpp"),
                   str(package / ("fault_board" + suffix)), f"-Wl,-rpath,{package}", "-o", str(executable)]
    with (root / "firmware-build.log").open("wb") as log:
        subprocess.run(command, cwd=root, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    env = dict(os.environ)
    env["PATH"] = str(package) + os.pathsep + str(engine.parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run([str(executable)], cwd=root, env=env, check=True,
                            capture_output=True, text=True, timeout=30)
    scenarios = ((None, None), ("gate_source_shunt", 0.01), ("drain_source_shunt", 0.01),
                 ("drain_source_shunt", 10.0), ("shifted_vto", 6.0))
    with BoardLibrary(manifest, engine_library=engine).create() as board:
        comparisons = []
        for fault, value in scenarios:
            board.reset()
            if fault is not None:
                board.inject_fault(fault, value)
            board.step(1e-6)
            compiled = board.read("drain_v")
            native = native_value(engine, project, faults, fault, value)
            if abs(compiled - native) > 1e-10:
                raise RuntimeError(f"Native/compiled mismatch for {fault}: {native} vs {compiled}")
            comparisons.append({"fault": fault or "normal", "value": value,
                                "native_internal_v": native, "compiled_v": compiled})
        board.reset()
        response = ParameterResponse(
            fault_site="shifted_vto", part_number="SPIKE-DEMO-NMOS", manufacturer="SPIKE",
            axis="dose_rad_si", reference=0.0, coefficient=5e-5, baseline=1.0,
            minimum_exposure=0.0, maximum_exposure=100000.0, parameter_unit="V",
            source_locator="scenario://compiled-board-fault-demo/dose-vto",
            conditions="Unverified fixed-bias what-if at the fixture's static operating point.",
            applicability_basis="Synthetic coefficient selected to exercise the bounded mapping only.")
        environment = response.apply(board, Exposure(300.15, dose_rad_si=100000.0),
                                     part_number="SPIKE-DEMO-NMOS", manufacturer="SPIKE")
        board.step(1e-6)
        environment["compiled_drain_v"] = board.read("drain_v")
        board.reset()
        campaign = FaultCampaign(board, board.library.fault_sites.values(), (
            FaultEvent(1e-6, "gate_source_shunt", 0.01),
            FaultEvent(2e-6, "gate_source_shunt", None),
        ), minimum_step_s=1e-9, maximum_step_s=1e-6, maximum_steps=10)
        campaign.advance_to(1e-6); campaign.save(); campaign.advance_to(2e-6)
        first_fault_v = board.read("drain_v")
        campaign.restore(); campaign.advance_to(2e-6)
        replay_fault_v = board.read("drain_v")
        if abs(first_fault_v - replay_fault_v) > 1e-10 or first_fault_v < 4.9:
            raise RuntimeError("Compiled fault campaign replay mismatch")
        scheduled = {"trace": campaign.trace, "first_fault_v": first_fault_v,
                     "replay_fault_v": replay_fault_v}
    (root / "python-comparison.json").write_text(json.dumps(comparisons, indent=2) + "\n", encoding="utf-8")
    (root / "environment-and-campaign.json").write_text(
        json.dumps({"environment": environment, "campaign": scheduled}, indent=2) + "\n", encoding="utf-8")
    (root / "firmware-output.txt").write_text(result.stdout, encoding="utf-8")
    print(result.stdout.strip())
    print(json.dumps(comparisons, indent=2))
    print(f"Board manifest: {manifest}")


if __name__ == "__main__":
    main()
