#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independently authored STEP fixtures using the admitted optional OCC runtime.

Development benchmark only; no third-party geometry or code is copied and no
general CAD authoring or redistributable mesher is provided.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_worker():
    """Fixed trusted shapes only; never executes user geometry/script text."""
    import ctypes.util
    import os
    from python.spike_core.gmsh_occ_runtime import API, DLL, verify_installation

    verify_installation()
    with os.add_dll_directory(str(DLL.parent)):
        previous = ctypes.util.find_library
        try:
            ctypes.util.find_library = lambda name: str(DLL) if name in ("gmsh", "gmsh-4.15") else previous(name)
            spec = importlib.util.spec_from_file_location("gmsh", API)
            gmsh = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gmsh)
        finally:
            ctypes.util.find_library = previous
        gmsh.initialize(["gmsh", "-nopopup"], readConfigFiles=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.option.setNumber("General.NumThreads", 1)
            gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
            for name in ("box", "sheared_duct", "cylinder"):
                gmsh.model.add(name)
                occ = gmsh.model.occ
                if name == "cylinder":
                    occ.addCylinder(0., 0., 0., 2., 0., 0., .5)
                else:
                    tag = occ.addBox(0., 0., 0., 2., 1., .5)
                    if name == "sheared_duct":
                        occ.affineTransform([(3, tag)], [
                            1., .25, 0., 0., 0., 1., 0., 0.,
                            0., 0., 1., 0., 0., 0., 0., 1.])
                occ.synchronize()
                gmsh.write(name + ".step")
                gmsh.model.remove()
        finally:
            gmsh.finalize()


def generate(output):
    from python.spike_core.gmsh_occ_runtime import verify_installation, _worker_interpreter
    from python.spike_core.gmsh_environment import isolated_preflight_source
    from python.spike_core.sparselizard_process import run_adapter_process

    provenance = verify_installation()  # Never bypass a changed entry hash.
    output = output.resolve()
    output.mkdir(parents=True)
    executable, packages = _worker_interpreter()
    source = isolated_preflight_source(ROOT, packages) + (
        "from scripts.generate_cfd_step_fixtures import fixture_worker\nfixture_worker()\n")
    process = run_adapter_process(
        [str(executable), "-I", "-S", "-c", source], cwd=output,
        timeout_s=60, memory_limit_mb=2048, output_limit_bytes=64*1024**2,
        stream_limit_bytes=2*1024**2)
    (output / "worker.log").write_text(process["stdout"]+process["stderr"], encoding="utf-8")
    if process["return_code"] != 0:
        raise RuntimeError("STEP fixture process failed; inspect worker.log")
    files = {name: {"file": name+".step", "sha256": sha(output / (name+".step"))}
             for name in ("box", "sheared_duct", "cylinder")}
    manifest = {"contract": "spike/cfd-step-fixtures/v1", "fixtures": files,
                "runtime_provenance": provenance,
                "environment": json.loads((output / "environment.json").read_text()),
                "memory_limit_enforced": process["memory_limit_enforced"],
                "job_assignment_race_closed": process.get("job_assignment_race_closed", False),
                "generator_sha256": sha(Path(__file__)),
                "independently_authored_geometry": True, "production_qualified": False,
                "limitations": ["Fixed mathematical fixtures, not CAD volume extraction",
                                "Existing local-development-only external OCC engine",
                                "No filesystem sandbox or transitive-DLL/release qualification"]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh fixture directory")
    manifest = generate(parser.parse_args().output)
    print(json.dumps({"fixtures": list(manifest["fixtures"]),
                      "memory_limit_enforced": manifest["memory_limit_enforced"]}))


if __name__ == "__main__":
    main()
