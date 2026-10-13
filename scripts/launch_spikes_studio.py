"""Run the development workbench against the owned SPIKES C++ library."""
from pathlib import Path
import os
import sys


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"standalone/spikes_project/studio/python"))
deps=ROOT/".tmp/studio-deps"
if deps.exists() and any((deps/'numpy'/'_core').glob(
        f'*.cp{sys.version_info.major}{sys.version_info.minor}-*.pyd')):
    # Development cache can contain a different Python ABI. Never shadow a
    # working system NumPy/Matplotlib with incompatible cached native wheels.
    sys.path.insert(0,str(deps))
os.environ.setdefault("MPLCONFIGDIR",str(ROOT/".tmp/studio-matplotlib"))

if __name__=="__main__":
    # Spawned native batch workers must not initialize wx/Matplotlib again.
    from spikes_studio.desktop import main
    arguments=sys.argv[1:]
    if "--library" not in arguments:
        for candidate in (ROOT/"build-spikes-native-analysis-20261013/Release/spikes_c_api.dll",ROOT/"build-spikes-adaptive-20261010/Release/spikes_c_api.dll",ROOT/"build-spikes-current-vs18-20260906/Release/spikes_c_api.dll",ROOT/"build-spikes-standalone-beta1-vs/spikes_c_api.dll",ROOT/"build-spikes-public-beta1/spikes_c_api.dll"):
            if candidate.exists():arguments=["--library",str(candidate),*arguments];break
    raise SystemExit(main(arguments))
