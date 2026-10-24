# SPDX-License-Identifier: Apache-2.0
"""Editable firstparty topology/placement candidate, explicitly not fab ready.

Run with installed KiCad 10 Python. Native pcbnew owns PCB serialization.
Schematic objects are emitted from explicit symbols/pins/wires, not substitutions.
"""
from pathlib import Path
import json,uuid,sys,math
import pcbnew as k
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=ROOT/'output/promo-planar-magnetics-20261023/converter'
OUT.mkdir(parents=True,exist_ok=True);(HERE/'Carrier.pretty').mkdir(exist_ok=True);(HERE/'models').mkdir(exist_ok=True)
def uid():return str(uuid.uuid4())
def q(s):return json.dumps(str(s))
def effects(size=1.0,justify=''):return f'(effects(font(size {size} {size})){justify})'
def property(name,value,x,y,hide=False):return f'(property {q(name)} {q(value)} (at {x} {y} 0) (effects(font(size 1 1)){"(hide yes)" if hide else ""}))'
pins2=[('1','1',-5.08,0,0),('2','2',5.08,0,180)]
pinsq=[('1','G',-7.62,0,0),('2','D',0,7.62,270),('3','S',0,-7.62,90)]
def connector_pins(n):return [(str(i+1),str(i+1),-7.62,(n-1)*1.27-i*2.54,0) for i in range(n)]
tpins=[('1','P1',-10.16,2.54,0),('2','P2',-10.16,-2.54,0)]
tpins += [(str(i),'S1' if i==3 else '~',10.16,2.54,180) for i in range(3,19)]
tpins += [(str(i),'S2' if i==19 else '~',10.16,-2.54,180) for i in range(19,35)]
symbols={'Passive2':pins2,'Generic_NMOS_GDS':pinsq,'Connector2':connector_pins(2),'Connector8':connector_pins(8),'Connector16':connector_pins(16),'PlanarT1':tpins}
def library_symbol(name,pins,standalone=False):
    height=max(2.54,max(abs(p[3]) for p in pins)-2.54)
    body=f'(rectangle(start -3.81 {height})(end 3.81 {-height})(stroke(width .254)(type default))(fill(type background)))'
    if name=='Generic_NMOS_GDS':
        body+='(text "NMOS" (at 0 0 0)(effects(font(size .8 .8))))'
    if name=='PlanarT1':body+='(text "8 : 1" (at 0 0 0)(effects(font(size 1 1))))(circle(center -2.54 1.9)(radius .4)(stroke(width .15)(type default))(fill(type outline)))(circle(center 2.54 -1.9)(radius .4)(stroke(width .15)(type default))(fill(type outline)))'
    pinrows=[]
    for num,label,x,y,angle in pins:
        hide=' (hide yes)' if name=='PlanarT1' and int(num)>3 and int(num)!=19 else ''
        pinrows.append(f'(pin passive line(at {x} {y} {angle})(length 3.81){hide}(name {q(label)}(effects(font(size .9 .9))))(number {q(num)}(effects(font(size .9 .9)))))')
    return f'(symbol {q(name if standalone else "Carrier:"+name)}(pin_names(offset .508))(in_bom yes)(on_board yes){property("Reference","U",0,-5)}{property("Value",name,0,5)}(symbol {q(name+"_0_1")}{body})(symbol {q(name+"_1_1")}{"".join(pinrows)}))'

components=[]
def part(ref,value,symbol,x,y,nets,footprint,boardxy):
    components.append(dict(ref=ref,value=value,symbol=symbol,x=round(round(x/1.27)*1.27,6),y=round(round(y/1.27)*1.27,6),nets={str(i):n for i,n in nets.items()},footprint=footprint,boardxy=boardxy,uuid=uid()))
part('J1','48V INPUT / geometry only','Connector2',30,45,{1:'VIN48',2:'PGND'},'Header1x2',(26,5))
for ref,g,d,s,pos,xy in [('Q1','GP1','VIN48','PRI_A',(65,50),(12,20)),('Q2','GP2','PRI_A','PGND',(65,85),(12,36)),('Q3','GP3','VIN48','PRI_B',(110,50),(12,52)),('Q4','GP4','PRI_B','PGND',(110,85),(12,68)),('Q5','GS1','RECT','SEC_A',(240,50),(88,20)),('Q6','GS2','RECT','SEC_B',(290,50),(88,36)),('Q7','GS3','SEC_A','SGND',(240,85),(88,52)),('Q8','GS4','SEC_B','SGND',(290,85),(88,68))]:
    part(ref,'NMOS placeholder / qualify separately','Generic_NMOS_GDS',*pos,{1:g,2:d,3:s},'MOS_GDS_GeometryOnly',xy)
part('T1','ELP32 N97 / 8:1 / 364.8uH nominal','PlanarT1',175,65,{1:'PRI_A',2:'PRI_B',**{i:'SEC_A' for i in range(3,19)},**{i:'SEC_B' for i in range(19,35)}},'PlanarTransformer_Module',(50,45))
part('C1','Input decoupling / value TBD','Passive2',35,110,{1:'VIN48',2:'PGND'},'Passive2_GeometryOnly',(8,80))
part('L1','1uH / saturation+loss TBD','Passive2',315,140,{1:'RECT',2:'VOUT18'},'Inductor_GeometryOnly',(48,81))
part('C2','1000uF / ESR+ripple TBD','Passive2',355,140,{1:'VOUT18',2:'SGND'},'Passive2_GeometryOnly',(61,81))
part('J2','1.8V OUTPUT / 8 pins each net','Connector16',385,140,{**{i:'VOUT18' for i in range(1,9)},**{i:'SGND' for i in range(9,17)}},'Header2x8',(70,85))
part('J3','External primary driver: G/S pairs','Connector8',75,165,dict(enumerate(['GP1','PRI_A','GP2','PGND','GP3','PRI_B','GP4','PGND'],1)),'GatePads2x4_P5',(3,5))
part('J4','External secondary driver: G/S pairs','Connector8',260,165,dict(enumerate(['GS1','SEC_A','GS2','SEC_B','GS3','SGND','GS4','SGND'],1)),'GatePads2x4_P5',(81,5))
rootid=uid();sch=['(kicad_sch(version 20250114)(generator "SPIKE_native_topology_writer")',f'(uuid {rootid})(paper "A3")','(title_block(title "48V to 1.8V 50W planar converter - topology / placement candidate")(rev "EXPERIMENTAL - NOT FAB READY"))','(lib_symbols'+''.join(library_symbol(n,p) for n,p in symbols.items())+')']
for c in components:
    name=c['symbol'];x,y=c['x'],c['y']
    sch.append(f'(symbol(lib_id {q("Carrier:"+name)})(at {x} {y} 0)(unit 1)(in_bom yes)(on_board yes)(dnp no)(uuid {c["uuid"]})'+property('Reference',c['ref'],x,y-12)+property('Value',c['value'],x,y+12)+property('Footprint','Carrier:'+c['footprint'],x,y,True)+''.join(f'(pin {q(num)}(uuid {uid()}))' for num,*_ in symbols[name])+f'(instances(project "carrier"(path "/{rootid}"(reference {q(c["ref"])})(unit 1)))))')
    emitted=set()
    for num,label,dx,dy,angle in symbols[name]:
        net=c['nets'][num];px,py=x+dx,y-dy
        if (px,py,net) in emitted:continue
        emitted.add((px,py,net));vx=-2.54 if dx<0 else 2.54 if dx>0 else 0;vy=0 if dx else (-2.54 if dy>0 else 2.54)
        ex,ey=px+vx,py+vy
        sch.append(f'(wire(pts(xy {px} {py})(xy {ex} {ey}))(stroke(width 0)(type default))(uuid {uid()}))')
        sch.append(f'(label {q(net)}(at {ex} {ey} 0){effects(1,"(justify left bottom)")}(uuid {uid()}))')
for text,x,y,size in [('PRIMARY FULL BRIDGE - external gate driver',45,20,2),('TRANSFORMER MODULE',145,20,2),('SYNCHRONOUS RECTIFIER - external gates',225,20,2),('OUTPUT LC + CPU-LIKE EXTERNAL LOAD',285,115,2),('Carrier uses 0.5mm study traces. Pins/footprints/current capacity UNQUALIFIED - not fabrication ready.',25,225,1.5),('Berg strips: geometry only; 27.8A output current, paralleling/contact sharing UNQUALIFIED.',25,233,1.5),('Driver timing, deadtime, startup, protection, isolation and thermal design remain required.',25,241,1.5),('Native circuit simulation uses prescribed bridge voltage and ideal rectifier abstraction, not these physical MOSFETs.',25,249,1.5)]:
    sch.append(f'(text {q(text)}(at {x} {y} 0){effects(size,"(justify left bottom)")}(uuid {uid()}))')
sch.append(')');(HERE/'carrier.kicad_sch').write_text('\n'.join(sch))

# Local firstparty footprint library. Geometry is explicitly unqualified.
def fp(name,pads,w=10,h=6,model=None):
    x0,y0,x1,y1=-w/2,-h/2,w/2,h/2
    if name.startswith(('Header','GatePads')):
        x0,y0=min(p[1] for p in pads)-1.6,min(p[2] for p in pads)-1.6
        x1,y1=max(p[1] for p in pads)+1.6,max(p[2] for p in pads)+1.6
    rows=[f'(footprint {q(name)}(version 20241229)(generator "SPIKE")(layer "F.Cu")',f'(property "Reference" "REF**"(at 0 {y0-1.5} 0)(layer "F.SilkS")(effects(font(size 1 1)(thickness .15))))',f'(property "Value" {q(name)}(at 0 {y1+1.5} 0)(layer "F.Fab")(effects(font(size 1 1)(thickness .15))))',f'(fp_rect(start {x0} {y0})(end {x1} {y1})(stroke(width .15)(type default))(fill none)(layer "F.SilkS"))',f'(fp_rect(start {x0-.25} {y0-.25})(end {x1+.25} {y1+.25})(stroke(width .05)(type default))(fill none)(layer "F.CrtYd"))']
    for num,x,y in pads:rows.append(f'(pad {q(num)} thru_hole circle(at {x} {y})(size 2.0 2.0)(drill 1.0)(layers "*.Cu" "*.Mask"))')
    if model:rows.append(f'(model {q(model)}(offset(xyz 0 0 0))(scale(xyz 1 1 1))(rotate(xyz 0 0 0)))')
    rows.append(')');(HERE/'Carrier.pretty'/f'{name}.kicad_mod').write_text('\n'.join(rows))
fp('MOS_GDS_GeometryOnly',[(1,-2.54,0),(2,0,0),(3,2.54,0)],10,6)
fp('Passive2_GeometryOnly',[(1,-2.54,0),(2,2.54,0)],8,8)
fp('Inductor_GeometryOnly',[(1,-6,0),(2,6,0)],15,12)
fp('Header1x2',[(1,0,0),(2,2.54,0)],7.62,5)
for n in (8,16):fp(f'Header2x{n//2}',[(i+1,(i//2)*2.54,(i%2)*2.54) for i in range(n)],n/2*2.54+2.54,6)
fp('GatePads2x4_P5',[(i+1,(i//2)*5.08,(i%2)*5.08) for i in range(8)],34,15)
pads=[(1,-20,-1.27),(2,-20,1.27)]
xs=[-8.89,-6.35,-3.81,-1.27,1.27,3.81,6.35,8.89]
pads += [(3+row*8+i,x,20+row*2.54) for row in range(2) for i,x in enumerate(xs)]
pads += [(19+row*8+i,x,-20-row*2.54) for row in range(2) for i,x in enumerate(xs)]
fp('PlanarTransformer_Module',pads,50,50,'${KIPRJMOD}/models/planar_transformer_assembly.step')
(HERE/'fp-lib-table').write_text('(fp_lib_table\n (version 7)\n (lib (name "Carrier") (type "KiCad") (uri "${KIPRJMOD}/Carrier.pretty") (options "") (descr "Original illustrative geometry; ratings unqualified"))\n)\n')
(HERE/'sym-lib-table').write_text('(sym_lib_table\n (version 7)\n (lib (name "Carrier") (type "KiCad") (uri "${KIPRJMOD}/Carrier.kicad_sym") (options "") (descr "Original abstract topology symbols"))\n)\n')
(HERE/'Carrier.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "SPIKE")\n'+''.join(library_symbol(n,p,True) for n,p in symbols.items())+')\n')
(HERE/'carrier.kicad_pro').write_text(json.dumps({'board':{'design_settings':{'rules':{'min_clearance':.25,'min_track_width':.25}}},'meta':{'filename':'carrier.kicad_pro','version':3},'net_settings':{'classes':[{'name':'Default','clearance':.25,'track_width':.5,'via_diameter':.8,'via_drill':.4}],'meta':{'version':3}}},indent=2))
board=k.BOARD();nets={name:k.NETINFO_ITEM(board,'/'+name) for name in sorted({n for c in components for n in c['nets'].values()})}
for n in nets.values():board.Add(n)
def v(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
for c in components:
    f=k.FootprintLoad(str(HERE/'Carrier.pretty'),c['footprint']);f.SetReference(c['ref']);f.SetValue(c['value']);f.SetPosition(v(*c['boardxy']));f.SetFPID(k.LIB_ID('Carrier',c['footprint']))
    f.SetPath(k.KIID_PATH('/'+rootid+'/'+c['uuid']));f.Value().SetVisible(False)
    for pad in f.Pads():pad.SetNet(nets[c['nets'][pad.GetNumber()]])
    board.Add(f)
def edge(x1,y1,x2,y2):
    s=k.PCB_SHAPE();s.SetShape(k.SHAPE_T_SEGMENT);s.SetStart(v(x1,y1));s.SetEnd(v(x2,y2));s.SetLayer(k.Edge_Cuts);s.SetWidth(k.FromMM(.05));board.Add(s)
for a,b in [((0,0),(100,0)),((100,0),(100,90)),((100,90),(0,90)),((0,90),(0,0))]:edge(*a,*b)
for a,b in [((33.75,34.45),(66.25,34.45)),((66.25,34.45),(66.25,55.55)),((66.25,55.55),(33.75,55.55)),((33.75,55.55),(33.75,34.45))]:edge(*a,*b)
for text,x,y in [('48V / 1.8V 50W TOPOLOGY STUDY - NOT FAB READY',50,3),('T1 50x50 module / lower-core CUTOUT 32.5x21.1',50,74),('ALL CONNECTOR CURRENTS UNQUALIFIED',50,88)]:
    t=k.PCB_TEXT(board);t.SetText(text);t.SetPosition(v(x,y));t.SetTextSize(v(.9,.9));t.SetTextThickness(k.FromMM(.15));t.SetLayer(k.Dwgs_User if text.startswith('T1 ') else k.F_SilkS);board.Add(t)
# Component keepout border only; copper escape is not certified by this drawing.
for a,b in [((24,19),(76,19)),((76,19),(76,71)),((76,71),(24,71)),((24,71),(24,19))]:
    s=k.PCB_SHAPE();s.SetShape(k.SHAPE_T_SEGMENT);s.SetStart(v(*a));s.SetEnd(v(*b));s.SetLayer(k.Dwgs_User);s.SetWidth(k.FromMM(.2));board.Add(s)
k.SaveBoard(str(HERE/'carrier.kicad_pcb'),board)
saved=k.LoadBoard(str(HERE/'carrier.kicad_pcb'))
expected={c['ref']:{pin:'/'+net for pin,net in c['nets'].items()} for c in components};actual={f.GetReference():{p.GetNumber():p.GetNetname() for p in f.Pads()} for f in saved.GetFootprints()}
assert expected==actual
(OUT/'native-generation.json').write_text(json.dumps({'kicad_version':k.Version(),'components':len(components),'pad_net_board_readback':'passed','expected_pin_nets':expected,'unrouted':True,'physical_cutout_mm':[32.5,21.1],'component_keepout_mm':[52,52],'keepout_is_documentary_border':True,'T1_model_path':'${KIPRJMOD}/models/planar_transformer_assembly.step','model_present':(HERE/'models/planar_transformer_assembly.step').exists()},indent=2)+'\n')
print(json.dumps({'components':len(components),'pads':sum(len(c['nets']) for c in components),'board_saved':True,'schematic_saved':True}))
