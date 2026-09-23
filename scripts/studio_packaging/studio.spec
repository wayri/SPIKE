import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

stage=Path(os.environ['SPIKES_STAGE'])
library=Path(os.environ['SPIKES_LIBRARY'])
a=Analysis([str(Path(SPECPATH)/'entry.py')],pathex=[str(stage)],
    binaries=[(str(library),'native')],datas=[(str(stage/'share'),'share')]+collect_data_files('plotly',includes=['package_data/plotly.min.js']),
    hiddenimports=collect_submodules('spikes_studio')+collect_submodules('python.spikes'),
    hookspath=[],hooksconfig={'matplotlib':{'backends':['WXAgg']}},
    excludes=['tkinter','PyQt4','PyQt5','PyQt6','PySide','PySide2','PySide6','pyqtgraph','qtpy','pyvistaqt','vtkmodules.qt','torch','tensorflow','pandas','IPython'],
    noarchive=False)
import sys
sys.path.insert(0,str(stage))
from spikes_studio.release_policy import qt_dependencies
blocked=qt_dependencies([entry[0] for entry in [*a.pure,*a.binaries,*a.datas]])
if blocked:raise RuntimeError('Qt-free packaging violation: '+', '.join(blocked))
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SPIKES-Studio',debug=False,strip=False,upx=False,console=os.name!='nt',icon=str(Path(SPECPATH)/'spikes-studio.ico') if os.name=='nt' else None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='SPIKES-Studio')
