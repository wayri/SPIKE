# SPDX-License-Identifier: Apache-2.0
"""Native STEP extraction; derived geometry retains CERN-OHL-W-2.0 source rights.
Run with FreeCADCmd; retains native-section JSON in the owned output folder.
"""
import json,hashlib,math,re,sys,os
from pathlib import Path

def extract(path,chord_deflection_mm=.015):
    import FreeCAD as App,Import,Part
    doc=App.newDocument('SpikeRealMotor');Import.insert(str(path),doc.Name)
    rows=[];coils=[];buses=[]
    cachepath=Path(path).resolve().parents[5]/'output/promo-propulsion-pod-20261023/real_motor/native-section.json'
    old={}
    if cachepath.is_file():
        cached=json.loads(cachepath.read_text())
        if cached.get('source_sha256')==hashlib.sha256(Path(path).read_bytes()).hexdigest() and cached.get('section_z_m')==0. and cached.get('length_unit')=='m':
            old={c['label']:c for c in cached['coils']}
    plane=Part.makePlane(500,500,App.Vector(-250,-250,0),App.Vector(0,0,1))
    for o in doc.Objects:
        if not hasattr(o,'Shape') or o.Shape.isNull() or not o.Shape.Solids:continue
        s=o.Shape.copy();s.Placement=o.getGlobalPlacement()
        label=o.Label
        take=(re.fullmatch(r'Tooth\d*',label) or re.fullmatch(r'Core\d*',label) or re.fullmatch(r'Magnet\d*',label) or re.fullmatch(r'Rotor\d*',label)) and len(s.Solids)==1
        if take:
            section=s.section(plane);wires=Part.sortEdges(section.Edges);loops=[]
            for edges in wires:
                wire=Part.Wire(edges);pts=wire.discretize(Deflection=chord_deflection_mm)
                loops.append([[p.x*.001,p.y*.001] for p in pts])
            rows.append({'label':label,'loops_m':loops,'volume_m3':s.Volume*1e-9,'center_m':[v*.001 for v in (sum((q.CenterOfMass*q.Volume for q in s.Solids),App.Vector())/sum(q.Volume for q in s.Solids))]})
        if re.fullmatch(r'Coil\d*',label) and len(s.Solids)==19:coils.append((label,s))
        if label in ('PhaseA','PhaseB','PhaseC','Null') or label.startswith('Connect'):buses.append((label,s))
    coil_rows=[]
    for label,s in coils:
        section=s.section(plane);loops=[]
        for edges in Part.sortEdges(section.Edges):
            wire=Part.Wire(edges);pts=wire.discretize(Deflection=.01)
            loops.append([[p.x*.001,p.y*.001] for p in pts])
        contacts=[]
        for blabel,b in buses:
            cached=next((v for v in old.get(label,{}).get('contacts',[]) if v['bus']==blabel),None)
            if cached is not None:
                contacts.append(cached);continue
            bb,cb=b.BoundBox,s.BoundBox
            gap=max(bb.XMin-cb.XMax,cb.XMin-bb.XMax,bb.YMin-cb.YMax,cb.YMin-bb.YMax,0.)
            if blabel.startswith('Connect') and gap>2.:continue
            distance,pairs,info=s.distToShape(b)
            contacts.append({'bus':blabel,'distance_m':distance*.001,'coil_point_m':[[v*.001 for v in pair[0]] for pair in pairs[:8]],'bus_point_m':[[v*.001 for v in pair[1]] for pair in pairs[:8]]})
        coil_rows.append({'label':label,'loops_m':loops,'volume_m3':s.Volume*1e-9,'contacts':contacts,'center_m':[v*.001 for v in (sum((q.CenterOfMass*q.Volume for q in s.Solids),App.Vector())/sum(q.Volume for q in s.Solids))]})
    return {'contract':'spike/openmotor-native-section/v1','source_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'freecad_version':App.Version(),'length_unit':'m','source_license':'CERN-OHL-W-2.0','section_z_m':0.,'chord_deflection_mm':chord_deflection_mm,'bodies':rows,'coils':coil_rows,'bus_labels':[b[0] for b in buses]}

if __name__=='__main__' or 'FreeCAD' in sys.modules:
    root=Path(__file__).resolve().parents[5]
    p=root/'examples/promo_showcase/propulsion_pod/real_hardware/OpenMotor125_25/CIAG_2_28 125_25.step'
    fine=os.environ.get('SPIKE_REAL_MOTOR_FINE')=='1'
    out=extract(p,.002 if fine else .015)
    target=root/('output/promo-propulsion-pod-20261023/real_motor/native-section-fine.json' if fine else 'output/promo-propulsion-pod-20261023/real_motor/native-section.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(out,separators=(',',':')),encoding='utf-8')
    print('SPIKE_REAL_MOTOR_GEOMETRY',len(out['bodies']),len(out['coils']),str(target))
