# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Admit original Cambridge measured two-wire Touchstone files and analyze them.

Data remains CC BY 4.0, not MIT. This does not establish geometric correlation.
Network downloads are opt-in and restricted to fixed original repository URLs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.sparameters import parse_touchstone_text, analyze_network

ITEM='https://api.repository.cam.ac.uk/server/api/core/items/31231488-051d-4828-a97f-b4daecca0125'
DOI='https://doi.org/10.17863/CAM.65674'
FILES={
 'Two_Wire_S31.S2P':('c93b656f-eb94-49f2-ac85-c41a31c23734','6b7d6e4c0814d28f68736ed1f5cb7526',149647,(1,3)),
 'Two_Wire_S32.S2P':('dae179b6-b85d-4518-942d-c7eb3351c73b','ab6e77c0fe215c9788002335e9111b06',149621,(2,3)),
 'Two_Wire_S41.S2P':('acce740c-b0fe-4106-92bd-9aa304f82b10','88dc8ca930708908b6ad8e8a842d70e5',149600,(1,4)),
 'Two_Wire_S42.S2P':('4d7375e2-fdcf-4c4a-a8fc-60fa1d4f2097','a611bc08c0419543c361cb36d2e98795',149640,(2,4)),
}


def admit_blob(name,payload):
    if name not in FILES or not isinstance(payload,bytes): raise ValueError('Unknown measured source')
    _,md5,size,_=FILES[name]
    if len(payload)!=size or hashlib.md5(payload).hexdigest()!=md5:
        raise ValueError('Published dataset size/checksum mismatch')
    network=parse_touchstone_text(payload.decode('ascii'),name)
    if network.port_count!=2 or not np.all(network.reference_impedance_ohm==50):
        raise ValueError('Expected measured 50-ohm two-port files')
    return network,hashlib.sha256(payload).hexdigest()


def partial_crosstalk(network):
    """Physical 1→4 is far-end coupling; physical 1→2 was not supplied."""
    transfer=network.s_parameters()[:,1,0]
    trace=[{'frequency_hz':float(f),'magnitude':float(abs(s)),
            'transfer_db':float(20*np.log10(max(abs(s),1e-300)))} for f,s in zip(network.frequencies_hz,transfer)]
    return {'contract':'spike/si-crosstalk-result/v1','status':'completed',
        'port_order':['physical1.near.wire1','physical2.near.wire2','physical3.far.wire1','physical4.far.wire2'],
        'mapping':{'next':'not supplied: physical 1→2','fext':'Measured physical 1→4; physical 2 and 3 terminated 50 ohm'},
        'next':{'status':'unsupported_missing_measurement','trace':[]},'fext':{'trace':trace},
        'complete_four_port_network':False,'geometry_or_field_coupling_claimed':False,
        'production_qualified':False}


def _fetch(url):
    with urlopen(url,timeout=90) as response:
        if not response.geturl().startswith('https://api.repository.cam.ac.uk/'):
            raise ValueError('Unexpected repository redirect')
        payload=response.read(2*1024**2+1)
    if len(payload)>2*1024**2: raise ValueError('Repository artifact exceeds budget')
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--download',action='store_true')
    parser.add_argument('--input',type=Path)
    args=parser.parse_args()
    if args.download == (args.input is not None): parser.error('Select --download or --input existing-data-directory')
    args.output.mkdir(parents=True,exist_ok=False)
    data=args.output/'data'; data.mkdir()
    metadata_bytes=_fetch(ITEM) if args.download else (args.input/'repository-item.json').read_bytes()
    metadata=json.loads(metadata_bytes)['metadata']
    rights=[row['value'] for row in metadata.get('dc.rights.uri',[])]
    if 'https://creativecommons.org/licenses/by/4.0/' not in rights: raise ValueError('Published license changed or missing')
    (data/'repository-item.json').write_bytes(metadata_bytes)
    provenance={'contract':'spike/measured-si-data-admission/v1','dataset_doi':DOI,
        'license':'CC-BY-4.0','license_url':rights[0],
        'authors':[row['value'] for row in metadata['dc.contributor.author']],
        'title':metadata['dc.title'][0]['value'],'instrument':'HP8722D two-port VNA',
        'geometry_summary':{'wire_length_m':.5,'wire_diameter_m':.0005,'wire_spacing_m_approximate':.01,
                            'launchers':'planar surface-wave launchers; full qualified geometry unavailable'},
        'uncertainty':'not quantitatively provided in admitted repository metadata',
        'geometry_correlation_qualified':False,'production_qualified':False,'files':{},
        'changes':'Original Touchstone bytes unchanged; SPIKE-derived reports are separate.',
        'repository_metadata_sha256':hashlib.sha256(metadata_bytes).hexdigest()}
    networks={}; reports={}
    for name,(uuid,md5,size,pair) in FILES.items():
        url=f'https://api.repository.cam.ac.uk/server/api/core/bitstreams/{uuid}/content'
        payload=_fetch(url) if args.download else (args.input/name).read_bytes()
        network,sha=admit_blob(name,payload)
        if not args.download:
            old=json.loads((args.input/'admission.json').read_text())
            if old['files'][name]['sha256']!=sha: raise ValueError('Pinned SHA256 admission mismatch')
        (data/name).write_bytes(payload)
        networks[name]=network
        reports[name]=analyze_network(network,trace_limit=None)
        provenance['files'][name]={'url':url,'sha256':sha,'publisher_md5':md5,'bytes':size,
            'touchstone_port_1_physical_port':pair[0],'touchstone_port_2_physical_port':pair[1],
            'other_physical_ports_terminated_ohm':50,'frequency_samples':len(network.frequencies_hz)}
        (args.output/(name+'.analysis.json')).write_text(json.dumps(reports[name],indent=2,allow_nan=False),encoding='utf-8')
    (data/'admission.json').write_text(json.dumps(provenance,indent=2,allow_nan=False),encoding='utf-8')
    (data/'ATTRIBUTION.txt').write_text(provenance['title']+'\n'+', '.join(provenance['authors'])+'\n'+DOI+'\nCC BY 4.0: '+rights[0]+'\n'+provenance['changes']+'\n',encoding='utf-8')
    measured=networks['Two_Wire_S41.S2P']
    analysis=reports['Two_Wire_S41.S2P']
    analysis['port_order']=['physical1.near.wire1','physical4.far.wire2']
    display={'contract':'spike/si-channel-result/v1','status':'completed','production_qualified':False,
        'compliance_status':'not_evaluated','network':analysis,'crosstalk':partial_crosstalk(measured),
        'provenance':provenance,'measurement_only':True,
        'limitations':['No physical 1→2 or 3→4 measurements: full four-port completion/NEXT/retermination forbidden.',
                      'Measured fixture response includes launchers; not deembedded or correlated to SPIKE geometry.']}
    (args.output/'measured-channel-result.json').write_text(json.dumps(display,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'status':'completed','dataset':DOI,'files':len(FILES),'sample_counts':{k:len(n.frequencies_hz) for k,n in networks.items()},
                      'geometry_correlation_qualified':False}))


if __name__=='__main__': raise SystemExit(main())
