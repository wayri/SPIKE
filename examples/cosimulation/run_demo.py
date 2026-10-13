# SPDX-License-Identifier: Apache-2.0
"""Synthetic co-simulation -> recorded twin example; no measured hardware data."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from python.spike_core.cosimulation import run_cosimulation
from python.spike_core.digital_twin import compare_digital_twin


def run_demo():
    folder = Path(__file__).resolve().parent
    simulation = run_cosimulation(json.loads((folder / "coupled-replay.json").read_text()))
    if simulation["status"] != "completed":
        raise RuntimeError(simulation["issues"])
    twin = json.loads((folder / "recorded-twin.json").read_text())
    twin["prediction"]["samples"] = [
        {"time_s": frame["time_s"], "values": {"voltage": frame["outputs"]["load"]["y"]}}
        for frame in simulation["frames"]]
    comparison = compare_digital_twin(twin)
    if comparison["status"] != "completed":
        raise RuntimeError(comparison["issues"])
    return {"cosimulation": simulation, "digital_twin": comparison}


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, allow_nan=False))
