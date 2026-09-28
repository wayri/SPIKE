# SPDX-License-Identifier: Apache-2.0
"""Frozen entry point for the dedicated release-owned circuit process."""

from pathlib import Path
import sys
import types


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The historical ``python.spikes`` package initializer exports the complete
# desktop analysis surface and consequently imports NumPy/PyArrow/plotting
# modules.  The circuit-only frozen process imports reviewed submodules
# directly and must not widen its dependency or attack surface through that
# initializer.  PyInstaller's importer can resolve collected submodules from a
# package shell whose path names their archived package location.
if getattr(sys, "frozen", False):
    frozen_root = Path(getattr(sys, "_MEIPASS")).resolve(strict=True)
    for package_name, archive_path in (
        ("python.spikes", "python/spikes"),
        ("python.spike_core", "python/spike_core"),
    ):
        if package_name not in sys.modules:
            circuit_package = types.ModuleType(package_name)
            circuit_package.__package__ = package_name
            circuit_package.__path__ = [str(frozen_root / Path(archive_path))]
            sys.modules[package_name] = circuit_package

from python.spike_core.owned_spice_process import main


if __name__ == "__main__":
    raise SystemExit(main())
