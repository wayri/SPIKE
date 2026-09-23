import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

stage=Path(os.environ['SPIKES_STAGE'])
library=Path(os.environ['SPIKES_LIBRARY'])
a=Analysis([str(Path(SPECPATH)/'entry.py')],pathex=[str(stage)],
    binaries=[(str(library),'native')],datas=[(str(stage/'share'),'share')],
    hiddenimports=collect_submodules('spikes_studio')+collect_submodules('python.spikes'),
    hookspath=[],hooksconfig={'matplotlib':{'backends':['WXAgg']}},
    excludes=['tkinter','PyQt5','PyQt6','PySide2','PySide6','torch','tensorflow','pandas','IPython'],
    noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SPIKES-Studio',debug=False,strip=False,upx=False,console=os.name!='nt',icon=str(Path(SPECPATH)/'spikes-studio.ico') if os.name=='nt' else None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='SPIKES-Studio')
