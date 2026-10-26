"""Compare frozen Python code with current source without executing either.

Use the build's exact Python interpreter. File names are normalized because
PyInstaller relocates them; instructions, constants and line tables must match.
Native libraries/data are covered separately by the packaged worker manifest.
"""
import argparse
import json
from pathlib import Path
import types

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
EM_COSIM_MODULES = {
    "python.spike_core.service_em_cosimulation", "python.spike_core.cli_em_cosimulation",
    "python.spike_core.solvers.execution.coupling.em_network_ac", "python.spike_core.solvers.execution.coupling.em_network_resistor_thermal",
    "python.spike_core.solvers.power_integrity.pdn.pdn_dielectric_ac", "python.spike_core.solvers.power_integrity.pdn.pdn_dielectric_thermomechanical",
    "extensions.emerge_suite.cosimulation",
    "extensions.emerge_suite.volume_capture",
    "python.spike_core.solvers.execution.coupling.em_spice_coupling", "python.spike_core.solvers.execution.coupling.em_spice_coupling_circuit",
    "python.spike_core.solvers.execution.coupling.em_body_heating", "python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_cht",
    "python.spike_core.solvers.execution.coupling.em_network_resistor_cht", "python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_energy",
    "python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_stokes", "python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_mesh",
    "python.spike_core.numerical_runtime",
    "python.spike_core.solvers.thermal_fluid.flow.native_cavity_momentum",
}


SI_IBIS_SPATIAL_MODULES = {
    "python.spike_core.service_ibis_behavioral",
    "python.spike_core.service_si_spatial",
    "python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral",
    "python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral_tables",
    "python.spike_core.solvers.signal_integrity.receivers.ibis_behavioral_execution",
    "python.spike_core.solvers.signal_integrity.receivers.si_ibis",
    "python.spike_core.solvers.signal_integrity.lines.rlgc_coupled_pair",
}


def normalized(code):
    return code.replace(co_filename="", co_consts=tuple(
        normalized(value) if isinstance(value, types.CodeType) else value
        for value in code.co_consts))


def inspect_packaged_source_modules(executable, *, source_root=None, require_em_cosimulation=False,
                                    require_si_ibis_spatial=False):
    """Return a strict comparison report; never import the packaged application."""
    root = Path(source_root) if source_root is not None else ROOT
    archive = CArchiveReader(str(executable)).open_embedded_archive("PYZ.pyz")
    checked, changed, missing = [], [], []
    for name in sorted(archive.toc):
        if name != "python" and not name.startswith("python.") and not (
                require_em_cosimulation and name in EM_COSIM_MODULES):
            continue
        base = root.joinpath(*name.split("."))
        source = base.with_suffix(".py")
        if not source.is_file():
            source = base / "__init__.py"
        if not source.is_file():
            missing.append(name)
            continue
        frozen = archive.extract(name)
        current = compile(source.read_bytes(), str(source), "exec", optimize=0)
        checked.append(name)
        # Code equality compares constants semantically. Marshaled byte streams
        # can differ only in frozenset ordering under different hash seeds.
        if normalized(frozen) != normalized(current):
            changed.append(name)
    required = set()
    if require_em_cosimulation:
        required.update(EM_COSIM_MODULES)
    if require_si_ibis_spatial:
        required.update(SI_IBIS_SPATIAL_MODULES)
    required_missing = sorted(required - set(checked))
    report = {"status": "passed" if checked and not changed and not missing and not required_missing else "failed",
              "checked_modules": len(checked), "changed": changed, "missing": missing,
              "required_missing": required_missing, "source_root": str(root.resolve())}
    return report


def verify_packaged_source_modules(executable, *, source_root=None, require_em_cosimulation=False,
                                    require_si_ibis_spatial=False):
    report = inspect_packaged_source_modules(
        executable, source_root=source_root, require_em_cosimulation=require_em_cosimulation,
        require_si_ibis_spatial=require_si_ibis_spatial)
    if report["status"] != "passed":
        raise RuntimeError("Packaged Python source coherence failed: " + json.dumps(report, sort_keys=True))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-root", type=Path, help="Explicit retained baseline; default is the active repository")
    parser.add_argument("--require-em-cosimulation", action="store_true", help="Reject a worker missing the integrated EM/AC/heat owners")
    parser.add_argument("--require-si-ibis-spatial", action="store_true",
                        help="Reject a worker missing the IBIS and supplied-RLGC spatial SI owners")
    args = parser.parse_args()
    report = inspect_packaged_source_modules(args.executable, source_root=args.source_root,
                                             require_em_cosimulation=args.require_em_cosimulation,
                                             require_si_ibis_spatial=args.require_si_ibis_spatial)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
