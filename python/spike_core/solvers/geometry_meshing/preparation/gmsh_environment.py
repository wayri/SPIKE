# SPDX-License-Identifier: Apache-2.0
"""Fixed dependency admission for isolated, declared local OCC environments.

The bootstrap does not process site or .pth files. Package roots are supplied
only by trusted interpreter selection, never a mesh request or environment
variable. This is dependency preflight, not complete DLL or release admission.
"""
from pathlib import Path


def isolated_preflight_source(root, packages):
    roots = [str(Path(path).resolve()) for path in packages]
    return f'''import sys, json, importlib
from pathlib import Path
sys.path.extend({roots!r})
report = {{'contract': 'spike/gmsh-environment/v1', 'status': 'checking',
          'interpreter': sys.executable, 'python_version': sys.version,
          'isolated': bool(sys.flags.isolated), 'site_disabled': bool(sys.flags.no_site),
          'package_directories': {roots!r}, 'dependencies': {{}}}}
try:
    for name in ('numpy', 'scipy', 'shapely'):
        try:
            module = importlib.import_module(name)
        except Exception as error:
            raise RuntimeError('GMSH_DEPENDENCY: ' + name + ': ' + str(error)) from error
        origin = Path(module.__file__).resolve()
        if not any(origin.is_relative_to(Path(path)) for path in report['package_directories']):
            raise RuntimeError('GMSH_DEPENDENCY: unexpected package origin for ' + name)
        report['dependencies'][name] = {{'version': str(module.__version__), 'origin': str(origin)}}
    report['status'] = 'passed'
except Exception as error:
    report['status'] = 'failed'
    report['diagnostic'] = str(error)
    Path('environment.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise
Path('environment.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
sys.path.insert(0, {str(Path(root).resolve())!r})
'''
