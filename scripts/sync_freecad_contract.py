"""Copy the dependency-free collaboration validator into the standalone workbench."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "python/spike_core/mcad_session_contract.py"
target = root / "integrations/freecad/SPIKEWorkbench/spike_freecad/session_contract.py"
target.write_bytes(source.read_bytes())
