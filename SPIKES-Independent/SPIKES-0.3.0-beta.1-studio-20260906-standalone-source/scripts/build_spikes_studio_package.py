"""Build isolated, relocatable Studio packages without touching SPIKE releases."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'scripts/studio_packaging'
TEMPLATE=ROOT/'standalone/spikes_project' if (ROOT/'standalone/spikes_project').is_dir() else ROOT


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def copy_tree(source,target):
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'),dirs_exist_ok=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--library',type=Path,required=True)
    p.add_argument('--deps-path',type=Path);p.add_argument('--iscc',type=Path);p.add_argument('--appimagetool',type=Path)
    args=p.parse_args();out=args.output.resolve();library=args.library.resolve(strict=True)
    if out.exists():raise FileExistsError('Choose a fresh output directory; existing releases are never overwritten')
    out.mkdir(parents=True);stage=out/'source';stage.mkdir()
    copy_tree(TEMPLATE/'python',stage/'python') if TEMPLATE!=ROOT else copy_tree(ROOT/'python',stage/'python')
    copy_tree(ROOT/'python/spikes',stage/'python/spikes')
    shutil.copy2(ROOT/'python/__init__.py',stage/'python/__init__.py')
    for name in ('acceleration.py','native_mna.py','contracts.py','ngspice_plugin.py','spice_netlist_safety.py','sparselizard_process.py'):
        shutil.copy2(ROOT/'python/spike_core'/name,stage/'python/spike_core'/name)
    copy_tree(TEMPLATE/'studio/python/spikes_studio',stage/'spikes_studio')
    for folder in ('docs','schemas','library'):
        copy_tree(TEMPLATE/'studio'/folder,stage/'share/spikes/studio'/folder)
    copy_tree(ROOT/'examples/spikes',stage/'share/spikes/examples')
    copy_tree(ROOT/'licenses',stage/'share/spikes/licenses/repository')
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name,stage/'share/spikes'/name)
    dependencies={}
    for name in ('pyinstaller','wxPython','matplotlib','numpy','scipy','pillow'):
        distribution=importlib.metadata.distribution(name);dependencies[name]=distribution.version
        for item in distribution.files or []:
            if 'license' in str(item).lower() or str(item).lower().endswith('copying'):
                path=Path(distribution.locate_file(item))
                if path.is_file():
                    target=stage/'share/spikes/licenses'/name/str(item).replace('../','')
                    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    if os.name!='nt':
        legal=Path('/usr/share/doc/python3-wxgtk4.0/copyright')
        if legal.is_file():shutil.copy2(legal,stage/'share/spikes/licenses/wxPython-copyright')
    sources=[{'path':v.relative_to(stage).as_posix(),'sha256':digest(v)} for v in sorted(stage.rglob('*')) if v.is_file()]
    (out/'source-manifest.json').write_text(json.dumps({'files':sources,'dependencies':dependencies,'native_sha256':digest(library)},indent=2),encoding='utf-8')
    env=dict(os.environ);paths=[str(stage)]
    if args.deps_path:paths.append(str(args.deps_path.resolve()))
    env.update(PYTHONPATH=os.pathsep.join(paths),SPIKES_STAGE=str(stage),SPIKES_LIBRARY=str(library))
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(out/'dist'),'--workpath',str(out/'work'),str(ASSETS/'studio.spec')]
    with (out/'freeze.log').open('w',encoding='utf-8') as log:subprocess.run(command,env=env,check=True,stdout=log,stderr=subprocess.STDOUT)
    payload=out/'dist/SPIKES-Studio';artifact=None
    if os.name=='nt' and args.iscc:
        with (out/'installer.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(args.iscc.resolve()),'/DPayload='+str(payload),'/DOutput='+str(out),str(ASSETS/'windows.iss')],check=True,stdout=log,stderr=subprocess.STDOUT)
        artifact=out/'SPIKES-Studio-0.3.0-beta.1-windows-x64-setup.exe'
    elif os.name!='nt' and args.appimagetool:
        appdir=out/'SPIKES-Studio.AppDir';copy_tree(payload,appdir/'usr/bin')
        for name in ('AppRun','spikes-studio.desktop','spikes-studio.svg','spikes-studio.png'):shutil.copy2(ASSETS/name,appdir/name)
        (appdir/'AppRun').chmod(0o755)
        artifact=out/'SPIKES-Studio-0.3.0-beta.1-linux-x86_64.AppImage'
        env.update(ARCH='x86_64',APPIMAGE_EXTRACT_AND_RUN='1')
        with (out/'appimage.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(args.appimagetool.resolve()),str(appdir),str(artifact)],env=env,check=True,stdout=log,stderr=subprocess.STDOUT)
    report={'product':'SPIKES Studio','version':'0.3.0-beta.1','channel':'unsigned-engineering-preview','signed':False,'dependencies':dependencies,'native_sha256':digest(library),'source_manifest_sha256':digest(out/'source-manifest.json'),'artifact':None}
    if artifact:report['artifact']={'name':artifact.name,'bytes':artifact.stat().st_size,'sha256':digest(artifact)}
    (out/'package-manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
