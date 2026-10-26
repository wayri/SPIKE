# SPDX-License-Identifier: Apache-2.0
"""Place exact native board inputs and portable project companions beside demos.

No simulation package, copper, schematic, library or existing project is edited.
Board-only inputs receive a clearly identified empty KiCad project launcher;
generated solid/machine examples retain an explicit no-KiCad-source declaration.
"""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from python.spike_core.project_package import read_project

def digest(data):return hashlib.sha256(data).hexdigest()
def text_digest(data):return digest(data.decode('utf-8-sig').replace('\r\n','\n').encode())
def write_exact(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file():
        if path.read_bytes()!=data:raise ValueError(f'Conflicting companion file: {path}')
    else:path.write_bytes(data)

def registry():
    planar=ROOT/'examples/promo_showcase/planar_magnetics'
    sources=[(ROOT/'app/public/demo/ebrake1.kicad_pcb','board-only original SPIKE input'),
      (ROOT/'examples/emerge/antenna_example.kicad_pcb','board-only original SPIKE teaching input'),
      (ROOT/'output/promo-esc-20261023/source/bldc-hardware-f1c65014d0caab5d99d888fc3025377861ac6ae2/design/BLDC_4.kicad_pcb','CC-BY-SA-4.0 legacy KiCad project'),
      (ROOT/'output/promo-drone-20261023/source/KiCad/ProPrj_IRIS.kicad_pcb','GPL-3.0 pinned native project; external component models excluded')]
    sources += [(planar/'windings'/name/(name+'.kicad_pcb'),'Apache-2.0 original winding-equivalent KiCad project') for name in ('primary','secondary','aircore_inductor')]
    sources += [(planar/'converter/carrier.kicad_pcb','Apache-2.0 original carrier KiCad project')]
    sources += [(ROOT/'build/curated-multiboard-20261005/arduino/converted'/name,'CC-BY-SA-4.0 converted board; source CAD archives retained') for name in ('uno.kicad_pcb','shield.kicad_pcb')]
    result={}
    for p,note in sources:
        if p.is_file():result[text_digest(p.read_bytes())]=(p,note)
    return result

def copy_project(board,folder,source_bytes,note):
    native_suffixes={'.kicad_pro','.kicad_sch','.kicad_sym','.kicad_mod','.kicad_dru','.pro','.sch','.lib','.dcm','.cmp','.step','.stp','.json','.md','.txt'}
    full=board.parent
    # Known complete original projects may contain independent local libraries.
    tree=board.stem in {'primary','secondary','aircore_inductor','carrier','ProPrj_IRIS','BLDC_4'}
    paths=full.rglob('*') if tree else full.iterdir()
    files=[]
    for p in paths:
        if not p.is_file():continue
        relative=p.relative_to(full)
        if any(part.startswith('.') or part in {'__pycache__','3D','3d','3dmodels','packages3d'} for part in relative.parts):continue
        if p==board:continue
        if p.suffix.lower() not in native_suffixes and p.name not in {'sym-lib-table','fp-lib-table','LICENSE','NOTICE'}:continue
        if not tree and not p.name.startswith(board.stem+'.'):continue
        write_exact(folder/relative,p.read_bytes());files.append(relative.as_posix())
    write_exact(folder/board.name,source_bytes);files.append(board.name)
    project=folder/(board.stem+'.kicad_pro')
    generated=not board.with_suffix('.kicad_pro').exists() and not board.with_suffix('.pro').exists()
    if generated:
        # KiCad's empty project settings select defaults; this is a new launcher,
        # never claimed as the project settings that produced the simulation.
        write_exact(project,b'{}\n');files.append(project.name)
    if board.stem in {'uno','shield'}:
        source=ROOT/'output/promo-showcase-20261023/electrical/arduino-cc-by-sa'
        for name in (('ABX00080-cad-files.zip','UNO-License.txt') if board.stem=='uno' else ('A000110-cad-files.zip','SHIELD-License.txt')):
            p=source/name
            if p.is_file():write_exact(folder/name,p.read_bytes());files.append(name)
    elif board.stem=='BLDC_4':
        for p,name in ((board.parent.parent/'README.md','UPSTREAM_README.md'),(ROOT/'output/promo-esc-20261023/source/CC-BY-SA-4.0.txt','CC-BY-SA-4.0.txt')):
            if p.is_file():write_exact(folder/name,p.read_bytes());files.append(name)
    else:
        for name in ('LICENSE','NOTICE'):
            if not (folder/name).exists():write_exact(folder/name,(ROOT/name).read_bytes());files.append(name)
    record={'source_board':str(board.relative_to(ROOT)).replace('\\','/'),'board_file':board.name,
      'embedded_board_sha256':digest(source_bytes),'original_board_sha256':digest(board.read_bytes()),
      'line_endings_only_difference':source_bytes!=board.read_bytes(),'provenance':note,
      'project_launcher_generated':generated,'schematic_included':any(Path(x).suffix in {'.kicad_sch','.sch'} for x in files),
      'files':sorted(set(files))}
    description=('This folder contains the exact KiCad board bytes embedded in the SPIKE project and available native companions.\n'
      +('The .kicad_pro is a generated empty launcher, not original simulation settings. No source schematic was available; none was fabricated.\n' if generated else 'Original project/schematic/library files are retained where available.\n')
      +'Preserve the attached license and source notes. External component 3D models are not added.\n')
    write_exact(folder/'SPIKE_SOURCE_README.txt',description.encode())
    return record

def colocate_tree(base):
    base=Path(base);known=registry();records=[]
    for project in sorted(base.rglob('*.spike')):
        opened=read_project(project,include_members=True)
        boards=[(name,data) for name,data in opened.members.items() if name.lower().endswith('.kicad_pcb')]
        companions=[]
        for member,data in boards:
            match=known.get(text_digest(data))
            if match is None:raise ValueError(f'Unknown KiCad source in {project}: {member}')
            source,note=match
            # Exact board copies are directly beside .spike; complete project
            # folders isolate each board's identically named local library tables.
            write_exact(project.parent/source.name,data)
            folder=project.parent/'KiCad'/source.stem
            record=copy_project(source,folder,data,note)
            record.update(project_folder=folder.relative_to(project.parent).as_posix(),
                          adjacent_board=source.name,package_member=member)
            assert digest((project.parent/source.name).read_bytes())==digest(data)
            companions.append(record)
        item={'spike_project':project.name,'spike_sha256':digest(project.read_bytes()),
          'kicad_sources':companions,'status':'co_located' if boards else 'not_applicable_no_kicad_input',
          'note':('Native board sources are beside this SPIKE file; use the KiCad project folders to preserve local libraries.' if boards else
                  'This is a generated solid-thermal or machine/reference model, not a KiCad-imported PCB. No KiCad project was used; none is invented.')}
        sidecar=project.with_suffix('.sources.json');sidecar.write_text(json.dumps(item,indent=2)+'\n',encoding='utf-8')
        records.append({'project':project.relative_to(base).as_posix(),'status':item['status'],'board_sources':len(companions),'sidecar':sidecar.relative_to(base).as_posix()})
    summary={'status':'passed','projects':records,'board_projects':sum(x['board_sources']>0 for x in records),'model_only_projects':sum(x['board_sources']==0 for x in records),
             'exact_embedded_source_checks':'all extracted adjacent board bytes SHA-256 matched embedded source bytes'}
    (base/'KICAD_SOURCE_INVENTORY.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return summary

if __name__=='__main__':
    for arg in sys.argv[1:]:
        r=colocate_tree(Path(arg));print(json.dumps({'root':arg,'board_projects':r['board_projects'],'model_only_projects':r['model_only_projects'],'status':r['status']}))
