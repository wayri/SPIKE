# SPIKE-Em study: emerge-demo4-patch-antenna
# emerge · upstream-example-native-wrapper
import json as _study_json
import os as _study_os
from pathlib import Path as _StudyPath
study_parameters = _study_json.loads("{\"Wpatch\":0.053,\"Lpatch\":0.052000000000000005,\"wline\":0.0032,\"wstub\":0.007,\"lstub\":0.0155,\"wsub\":0.1,\"hsub\":0.1,\"th\":0.001524,\"Rair\":0.1,\"f1\":1545000000,\"f2\":1605000000}")
study_resource_root = (_StudyPath(_study_os.environ.get('SPIKE_HOME') or _study_os.environ.get('SPIKE_WORKSPACE') or _StudyPath.cwd()) / "examples/upstream-emerge").resolve()
from pathlib import Path
import os, runpy
resource_root=Path(os.environ.get('SPIKE_HOME') or os.environ.get('SPIKE_WORKSPACE') or Path.cwd())
bridge=resource_root/'examples'/'upstream-emerge'/'bridge.py'
if not bridge.is_file():
    raise RuntimeError('EMerge example resources are unavailable; select a SPIKE-Em source/resource root with SPIKE_HOME')
# Desktop profile preserves geometry/frequencies, serializes sweep jobs and lets EMerge select an available solver.
execution_options={'serial_sweep': True, 'solver': 'AUTO', 'max_adaptive_steps': 2}
runpy.run_path(str(bridge))['run_example']('examples/demo4_patch_antenna.py', study_parameters, spike, execution_options)
