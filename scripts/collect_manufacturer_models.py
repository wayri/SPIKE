"""Bounded public model intake. Archives are inventoried, never executed/extracted."""
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.request
import urllib.parse
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
from spikes_studio.vendor_intake import inspect_text

HOSTS={'st':{'www.st.com'},'infineon':{'www.infineon.com'},'onsemi':{'www.onsemi.com','www.onsemi.cn'},
       'ti':{'www.ti.com'},'adi':{'www.analog.com'},'littelfuse':{'www.littelfuse.com'},
       'nexperia':{'assets.nexperia.com','www.nexperia.com'},'nxp':{'www.nxp.com'},
       'renesas':{'www.renesas.com'},'qorvo':{'www.qorvo.com'},'wolfspeed':{'www.wolfspeed.com'},
       'rohm':{'www.rohm.com','fscdn.rohm.com'},'toshiba':{'toshiba.semicon-storage.com'}}
LIMIT=16*1024*1024

def validate_url(url,vendor):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS[vendor] or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Only explicit HTTPS manufacturer hosts are permitted')

class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,vendor):self.vendor=vendor
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_url(newurl,self.vendor)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def inventory(raw):
    entries=[]
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info=archive.infolist()
            if len(info)>2000 or sum(i.file_size for i in info)>64*1024*1024:raise ValueError('Archive inventory exceeds bounds')
            for item in info:
                entry={'name':item.filename,'bytes':item.file_size}
                if item.file_size>2*1024*1024 or item.flag_bits&1:entry['status']='oversized_or_encrypted'
                elif Path(item.filename).suffix.lower() in {'.lib','.cir','.sp','.spi','.mod','.sub','.txt'}:
                    text=archive.read(item).decode('utf-8-sig',errors='replace')
                    try:
                        report=inspect_text(text,item.filename);report.pop('original_source',None)
                        entry.update(status='inventoried_not_executed',review=report)
                    except ValueError as exc:entry.update(status='not_model_text',reason=str(exc))
                else:entry['status']='retained_in_archive_only'
                entries.append(entry)
    else:
        report=inspect_text(raw.decode('utf-8-sig'), 'downloaded-model');report.pop('original_source',None)
        entries.append(dict(name='downloaded-model',review=report,status='inventoried_not_executed'))
    return entries

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vendor',choices=sorted(HOSTS),required=True)
    p.add_argument('--url',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    validate_url(args.url,args.vendor)
    request=urllib.request.Request(args.url,headers={'User-Agent':'SPIKES-ModelIntake/0.1 (public model compatibility research)'})
    with urllib.request.build_opener(Redirect(args.vendor)).open(request,timeout=30) as response:
        raw=response.read(LIMIT+1);final=response.url
    if len(raw)>LIMIT:raise ValueError('Download exceeds 16 MiB')
    entries=inventory(raw);digest=hashlib.sha256(raw).hexdigest()
    args.output.mkdir(parents=True,exist_ok=True)
    artifact=args.output/(digest+'.download')
    if not artifact.exists():artifact.write_bytes(raw)
    report=dict(contract='spikes/manufacturer-intake/v1',manufacturer=args.vendor,url=args.url,final_url=final,
        retrieved_utc=datetime.now(timezone.utc).isoformat(),sha256=digest,bytes=len(raw),entries=entries,
        execution='not_performed',qualification='not_qualified',redistribution='requires_license_review')
    path=args.output/(digest+'.json');path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(path),bytes=len(raw),entries=len(entries),
        models=sum(len(e.get('review',{}).get('models',[])) for e in entries),
        subcircuits=sum(len(e.get('review',{}).get('subcircuits',[])) for e in entries))))

if __name__=='__main__':main()
