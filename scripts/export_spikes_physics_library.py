# SPDX-License-Identifier: Apache-2.0
"""Export original generic SPICE models and separately importable symbols."""
import argparse
import hashlib
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]


def export(destination):
    from python.spikes.lumped_physics_parts import catalog,build
    from spikes_studio.device_symbols import symbols
    from spikes_studio.library_package import save,load
    from spikes_studio.document import write_json
    target=Path(destination)
    if target.exists():raise ValueError('Choose a new directory; existing exports are never overwritten')
    entries=[build(item['id'],name='SPK_'+item['id'].upper()) for item in catalog()]
    drawings=symbols()
    target.mkdir(parents=True)
    source='* SPDX-License-Identifier: Apache-2.0\n* Original generic lumped references, not qualified process models\n\n'+'\n'.join(item['source'] for item in entries)
    (target/'generic-lumped-physics.lib').write_text(source,encoding='ascii')
    write_json(target/'device-symbols.json',{'contract':'spikes/studio-symbol-library/v1','symbols':drawings})
    save(target/'device-symbols.spklib',[],drawings)
    load(target/'device-symbols.spklib')
    manifest={'contract':'spikes/lumped-physics-library/v1','license':'Apache-2.0',
              'models':[{key:item[key] for key in ('kind','name','pins','symbol_id','parameters','supported_analyses','model_status','limitations')} for item in entries],
              'files':{name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in ('generic-lumped-physics.lib','device-symbols.json','device-symbols.spklib')},
              'notice':'SPICE model and symbol libraries are separate. Import never qualifies a model. No spatial TCAD, foundry BiCMOS/PDK, or production four-terminal BJT claim.'}
    write_json(target/'manifest.json',manifest)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=export(args.output)
    print('Exported '+str(len(report['models']))+' generic models and 11 symbols to '+str(args.output))


if __name__=='__main__':main()
