"""Persistent schematic, property transactions, probes, and keyboard profiles."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import uuid


SCHEMATIC_CONTRACT = "spikes/schematic/v1"
RC_DECK = """SPIKES RC startup
V1 in 0 1
R1 in out 1k
C1 out 0 1u
.tran 10u 5m uic
.end
"""


def write_json(path, value):
    path = Path(path)
    encoded = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    # Same-directory replace keeps the last saved revision if writing fails.
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class Document:
    def __init__(self, data):
        self.data = deepcopy(data)
        self.data.setdefault('wires',[])
        from .model_fidelity import default_policy
        self.data.setdefault('model_policy', default_policy())
        self.data.setdefault('simulation_sequences',[])
        self.data.setdefault('annotations',[])
        from .dashboard import empty_dashboard
        self.data.setdefault('dashboard',empty_dashboard())
        for part in self.data.get('components',[]):
            part.setdefault('rotation',0)
            part.setdefault('mirror_x',False);part.setdefault('mirror_y',False)
        from .simulation_setup import default_thermal,default_profile
        self.data.setdefault('thermal_setup',default_thermal())
        self.data.setdefault('run_profile',default_profile())
        # v1 projects predate explicit backend selection. Their historical
        # execution was native, so migration must never select ngspice.
        self.data['run_profile'].setdefault('backend','native')
        from .plot_panes import default_layout
        self.data.setdefault('plot_layout',default_layout())
        self.data.setdefault('instruments',[])
        self.data.setdefault('controller_setup',None)
        from .power_tree import empty_tree
        self.data.setdefault('power_tree',empty_tree());self.data.setdefault('analytics_extensions',[])
        from .directives import reconcile
        self.data['directives']=reconcile(self.data['source'],self.data.get('directives',[]))
        self.undo_stack, self.redo_stack = [], []
        self.validate()
        self.saved_data = deepcopy(self.data)

    @property
    def dirty(self):
        return self.data != self.saved_data

    @classmethod
    def from_netlist(cls, source):
        from python.spikes.netlist import parse_netlist
        project = parse_netlist(source, native_extensions=True, transient_capture='rolling')
        parts = []
        from .pin_geometry import ordered_nodes
        for index, el in enumerate(project.elements):
            parts.append({"id": uuid.uuid4().hex, "ref": el.name, "kind": el.kind,
                "value": format(el.value, ".12g"), "nodes": ordered_nodes(el),
                "x": 140 + index % 4 * 200, "y": 180 + index // 4 * 160,
                "package": "", "variant": "fitted", "temperature_k": 300.15,
                "limits": {}, "model_source": "", "evidence": "", "parameters": {}})
        # Source is authoritative; properties mutate its exact top-level records.
        return cls({"contract": SCHEMATIC_CONTRACT, "id": uuid.uuid4().hex, "title": project.title,
                    "source": source, "components": parts, "probes": [], "expressions": [],
                    "metadata": {}, "revision": 0})

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > 16 * 1024 * 1024: raise ValueError("Schematic exceeds 16 MiB")
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path):
        self.validate()
        write_json(path, self.data)
        self.saved_data = deepcopy(self.data)

    def apply_source(self, source):
        """Reconcile authoritative source without discarding layout or metadata."""
        if source == self.data['source']:
            return
        replacement = Document.from_netlist(source)
        previous = {p['ref'].upper(): p for p in self.data['components']}
        for part in replacement.data['components']:
            old = previous.get(part['ref'].upper())
            if old and old['kind'] == part['kind']:
                for key in ('id', 'x', 'y', 'rotation', 'mirror_x', 'mirror_y', 'package', 'variant', 'temperature_k',
                            'limits', 'model_source', 'evidence', 'parameters'):
                    part[key] = deepcopy(old[key])
        def mutate(data):
            data.update(source=source, title=replacement.data['title'],
                        components=replacement.data['components'])
            parts={p['id']:p for p in data['components']}
            data['wires']=[w for w in data['wires'] if all(e[0] in parts and 0<=e[1]<len(parts[e[0]]['nodes']) for e in (w['a'],w['b'])) and parts[w['a'][0]]['nodes'][w['a'][1]].lower()==parts[w['b'][0]]['nodes'][w['b'][1]].lower()]
        self.commit(mutate)

    def rotate(self,ids):
        if not ids or set(ids)-{p['id'] for p in self.data['components']}:raise ValueError('Select components to rotate')
        def mutate(data):
            for p in data['components']:
                if p['id'] in ids:p['rotation']=(p['rotation']+90)%360
        self.commit(mutate)

    def connect(self,a,b,waypoints=None):
        """Merge complete named nets, never substitute a decorative line for wiring."""
        import re
        from .part_properties import rewrite
        parts={p['id']:p for p in self.data['components']}
        for endpoint in (a,b):
            if len(endpoint)!=2 or endpoint[0] not in parts or type(endpoint[1]) is not int or not 0<=endpoint[1]<len(parts[endpoint[0]]['nodes']):raise ValueError('Choose existing component terminals')
        if a==b:raise ValueError('Choose a different terminal')
        if any({tuple(w['a']),tuple(w['b'])}=={tuple(a),tuple(b)} for w in self.data['wires']):raise ValueError('These terminals already have a route')
        keep=parts[a[0]]['nodes'][a[1]];old=parts[b[0]]['nodes'][b[1]]
        if old=='0':keep,old=old,keep
        candidate=Document(self.data)
        if keep.lower()!=old.lower():
            if self.data['controller_setup'] is not None:raise ValueError('Detach the controller setup before merging named nets; its pin bindings need explicit review')
            source=self.data['source']
            if re.search(r'(?im)^\s*\.(subckt|include|lib|ic|nodeset|measure|meas|global)\b',source) or any(':' in p['ref'] for p in parts.values()):raise ValueError('Net merging for hierarchy/includes/node directives is not supported yet; edit their source explicitly')
            if re.search(r'(?i)\bv\s*\(',source):raise ValueError('Source contains voltage-reference expressions; edit and verify those nets explicitly')
            for p in parts.values():
                nodes=[keep if n.lower()==old.lower() else n for n in p['nodes']]
                if nodes!=p['nodes']:source=rewrite(source,p['ref'],{'nodes':nodes},None)
            candidate.apply_source(source)
            def rename(expression):
                return re.sub(r'(?i)\bv\(([^)]*)\)',lambda m:'V('+','.join(keep if n.strip().lower()==old.lower() else n.strip() for n in m[1].split(','))+')',expression)
            for probe in candidate.data['probes']:
                from python.spikes.contracts import ProbeDescriptor
                probe['expression']=rename(probe['expression']);probe['descriptor']=ProbeDescriptor.parse(probe['expression']).to_dict()
            for instrument in candidate.data['instruments']:instrument['expression']=rename(instrument['expression'])
            for instrument in candidate.data['dashboard']['widgets']:instrument['expression']=rename(instrument['expression'])
            candidate.data['expressions']=[rename(e) for e in candidate.data['expressions']]
        candidate.data['wires'].append({'id':uuid.uuid4().hex,'a':list(a),'b':list(b),'waypoints':list(waypoints or [])})
        candidate.data['revision']=self.data['revision']
        candidate.validate();self.commit(lambda d:d.update(deepcopy(candidate.data)))

    def mirror(self,ids,axis='horizontal'):
        """Reflect each selected symbol in world coordinates, retaining pin identity."""
        if axis not in ('horizontal','vertical'):raise ValueError('Mirror axis must be horizontal or vertical')
        if not ids or set(ids)-{p['id'] for p in self.data['components']}:raise ValueError('Select components to mirror')
        def mutate(data):
            for p in data['components']:
                if p['id'] in ids:
                    flip_x=(axis=='horizontal') != (p['rotation'] in (90,270))
                    key='mirror_x' if flip_x else 'mirror_y';p[key]=not p[key]
        self.commit(mutate)

    def move_wire_route(self,ident,dx,dy):
        from .editor_geometry import route
        wire=next(w for w in self.data['wires'] if w['id']==ident)
        points=route({p['id']:p for p in self.data['components']},wire)
        # Endpoint identities stay fixed; offset the route, with orthogonal leads.
        anchors=[[x+dx,y+dy] for x,y in points]
        def mutate(data):
            next(w for w in data['wires'] if w['id']==ident)['waypoints']=anchors
        self.commit(mutate)

    def edit_annotation(self,ident=None,*,kind='note',x,y,width=160,height=70,text='',color='accent'):
        """Create/update an inert canvas annotation; never inject simulation source."""
        if ident is not None and ident not in {a['id'] for a in self.data['annotations']}:raise ValueError('Annotation no longer exists')
        ident=ident or uuid.uuid4().hex
        item=dict(id=ident,kind=kind,x=x,y=y,width=width,height=height,text=text,color=color)
        def mutate(data):
            index=next((i for i,a in enumerate(data['annotations']) if a['id']==ident),None)
            if index is None:data['annotations'].append(item)
            else:data['annotations'][index]=item
        self.commit(mutate)
        return ident

    def remove_annotations(self,ids):
        if not ids or set(ids)-{a['id'] for a in self.data['annotations']}:raise ValueError('Select existing annotations')
        self.commit(lambda d:d.__setitem__('annotations',[a for a in d['annotations'] if a['id'] not in ids]))

    def move(self, positions):
        by_id = {p['id']: p for p in self.data['components']}
        if not positions or set(positions) - set(by_id):
            raise ValueError('Selection is empty or stale')
        def mutate(data):
            for part in data['components']:
                if part['id'] in positions:
                    part['x'], part['y'] = map(float, positions[part['id']])
        self.commit(mutate)

    def validate(self):
        from .model_fidelity import validate as validate_model_policy
        validate_model_policy(self.data['model_policy'])
        from .dashboard import validate_dashboard
        from .simulation_sequences import validate as validate_sequences
        validate_sequences(self.data['simulation_sequences'])
        validate_dashboard(self.data['dashboard'])
        from .library_browser import validate_preferences
        if not isinstance(self.data.get('metadata',{}),dict):raise ValueError('Project metadata must be an object')
        validate_preferences(self.data.get('metadata',{}).get('library_browser',{}))
        if self.data['controller_setup'] is not None:
            from .controller_block import validate as validate_controller
            validate_controller(self.data['controller_setup'])
        from .plot_workspace import validate_instruments
        validate_instruments(self.data['instruments'],self.data['components'])
        from .power_tree import validate as validate_power
        from .analytics import validate_extension
        validate_power(self.data['power_tree'])
        extensions=self.data['analytics_extensions']
        if not isinstance(extensions,list) or len(extensions)>32:raise ValueError('At most 32 analytics extensions per project')
        for extension in extensions:validate_extension(extension)
        if len({e['id'] for e in extensions})!=len(extensions):raise ValueError('Duplicate analytics extension ID')
        from .plot_panes import validate_layout
        validate_layout(self.data['plot_layout'])
        from .directives import validate
        validate(self.data['directives'],self.data['source'])
        from .simulation_setup import validate_thermal,validate_profile
        validate_thermal(self.data['thermal_setup']);validate_profile(self.data['run_profile'])
        if self.data.get("contract") != SCHEMATIC_CONTRACT: raise ValueError("Unsupported schematic version")
        for name in ('id','title','revision','components','probes','expressions','metadata'):
            if name not in self.data:raise ValueError(f'Missing schematic field: {name}')
        if not isinstance(self.data.get("source"), str): raise ValueError("Missing source netlist")
        parts = self.data["components"]
        if len(parts) > 100_000: raise ValueError("Too many components")
        for key in ("id", "ref"):
            ids = [p[key] for p in parts]
            if len(ids) != len(set(ids)): raise ValueError(f"Duplicate component {key}")
        for part in parts:
            if any(type(part.get(key)) is not bool for key in ('mirror_x','mirror_y')):raise ValueError('Mirror flags must be boolean')
            if type(part.get('rotation')) is not int or part['rotation'] not in (0,90,180,270):raise ValueError('Rotation must be 0, 90, 180 or 270 degrees')
            if any(not math.isfinite(float(part[k])) for k in ("x", "y", "temperature_k")): raise ValueError("Nonfinite component property")
            if part["temperature_k"] <= 0: raise ValueError("Temperature must be positive kelvin")
            for value in part["limits"].values():
                if not math.isfinite(float(value)) or float(value) <= 0: raise ValueError("Limits must be positive finite SI values")
        for probe in self.data["probes"]:
            from python.spikes.contracts import ProbeDescriptor
            ProbeDescriptor.parse(probe["expression"])
        annotations=self.data['annotations']
        if not isinstance(annotations,list) or len(annotations)>10000:raise ValueError('At most 10000 canvas annotations')
        seen=set()
        for a in annotations:
            if not isinstance(a,dict) or not isinstance(a.get('id'),str) or not a['id'] or a['id'] in seen:raise ValueError('Invalid or duplicate annotation ID')
            seen.add(a['id'])
            if a.get('kind') not in ('note','rect','ellipse'):raise ValueError('Unknown annotation kind')
            if any(type(a.get(k)) not in (int,float) or not math.isfinite(a[k]) or abs(a[k])>1e7 for k in ('x','y','width','height')):raise ValueError('Annotation geometry must be finite and bounded')
            if a['width']<=0 or a['height']<=0:raise ValueError('Annotation dimensions must be positive')
            if not isinstance(a.get('text'),str) or len(a['text'])>16384:raise ValueError('Annotation text exceeds 16384 characters')
            if a.get('color') not in ('accent','text','warning','danger'):raise ValueError('Unknown annotation theme color')
        by_id={p['id']:p for p in parts}
        if not isinstance(self.data['wires'],list) or len(self.data['wires'])>100000:raise ValueError('Invalid wire list')
        for wire in self.data['wires']:
            points=wire.get('waypoints',[])
            if not isinstance(points,list) or len(points)>2048:raise ValueError('Wire route exceeds 2048 corners')
            if any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in p) for p in points):raise ValueError('Invalid wire corner coordinates')
            for endpoint in (wire['a'],wire['b']):
                if len(endpoint)!=2 or endpoint[0] not in by_id or type(endpoint[1]) is not int or not 0<=endpoint[1]<len(by_id[endpoint[0]]['nodes']):raise ValueError('Invalid wire terminal')
            if by_id[wire['a'][0]]['nodes'][wire['a'][1]].lower()!=by_id[wire['b'][0]]['nodes'][wire['b'][1]].lower():raise ValueError('Wired terminals must share a net; use Undo or edit the circuit text to change connectivity')

    def update_setup(self,key,value):
        if key not in ('thermal_setup','run_profile'):raise ValueError('Unknown project setup section')
        self.commit(lambda data:data.__setitem__(key,deepcopy(value)))

    def commit(self, mutate):
        old = deepcopy(self.data)
        try:
            mutate(self.data)
            from .directives import reconcile
            self.data['directives']=reconcile(self.data['source'],self.data['directives'])
            self.validate()
            self.data["revision"] = old["revision"] + 1
        except Exception:
            self.data = old
            raise
        self.undo_stack.append(old)
        self.redo_stack.clear()

    def edit_directive(self,ident=None,*,text,enabled=True,group=None,title='',visible=True,x=None,y=None):
        from .directives import rewrite
        item=next((v for v in self.data['directives'] if v['id']==ident),None)
        if ident is not None and item is None:raise ValueError('Directive no longer exists')
        if not isinstance(enabled,bool):raise ValueError('Enabled must be boolean')
        source,line=rewrite(self.data['source'],item,text,enabled)
        # Reuse source reconciliation and native parser before committing one
        # atomic undoable transaction, including re-elaborated .param parts.
        candidate=Document(self.data);candidate.apply_source(source)
        target=next(v for v in candidate.data['directives'] if v['line']==line)
        target.update(id=ident or target['id'],group=group or target['group'],title=title,visible=visible)
        if x is not None:target['x']=x
        if y is not None:target['y']=y
        candidate.validate()
        self.commit(lambda data:data.update(deepcopy(candidate.data)))
        return target['id']

    def remove_directives(self,ids):
        from .directives import rewrite
        items=[v for v in self.data['directives'] if v['id'] in ids]
        if not items or len(items)!=len(set(ids)):raise ValueError('Select existing directives')
        source=self.data['source']
        for item in sorted(items,key=lambda v:v['line'],reverse=True):source,_=rewrite(source,item,None,False)
        self.apply_source(source)

    def organize_directives(self,ids,**changes):
        if set(changes)-{'group','visible','x','y'}:raise ValueError('Unsupported directive organization field')
        if not ids or set(ids)-{v['id'] for v in self.data['directives']}:raise ValueError('Select existing directives')
        def mutate(data):
            for item in data['directives']:
                if item['id'] in ids:item.update(changes)
        self.commit(mutate)

    def enable_directives(self,ids,enabled):
        from .directives import rewrite
        if not isinstance(enabled,bool):raise ValueError('Enabled must be boolean')
        items=[v for v in self.data['directives'] if v['id'] in ids]
        if not items or len(items)!=len(set(ids)):raise ValueError('Select existing directives')
        source=self.data['source']
        for item in sorted(items,key=lambda v:v['line'],reverse=True):source,_=rewrite(source,item,item['text'],enabled)
        self.apply_source(source)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.data)
            self.data = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.data)
            self.data = self.redo_stack.pop()

    def update(self, ids, changes, model=None):
        if not ids or set(ids) - {p["id"] for p in self.data["components"]}: raise ValueError("Selection is empty or stale")
        if set(changes) - {"value", "nodes", "package", "variant", "temperature_k", "limits", "model_source", "evidence", "parameters"}: raise ValueError("Unsupported property")
        def mutate(data):
            for part in data["components"]:
                if part["id"] not in ids: continue
                if "value" in changes or "nodes" in changes or model is not None:
                    from .part_properties import rewrite,form
                    data['source']=rewrite(data['source'],part['ref'],changes,model)
                    applied=form(data['source'],part['ref'])
                    part['value']=applied['value'];part['nodes']=applied['nodes']
                part.update(deepcopy(changes))
        self.commit(mutate)

    def add_probe(self, expression, anchor=None):
        from python.spikes.contracts import ProbeDescriptor
        probe = ProbeDescriptor.parse(expression)
        nodes = {n.lower() for p in self.data["components"] for n in p["nodes"]} | {"0"}
        if expression.lower().startswith("v("):
            refs = expression[2:-1].lower().split(",")
            if any(n.strip() not in nodes for n in refs): raise ValueError("Unknown probe node")
        else:
            ref = expression[2:-1].upper()
            if ref not in {p["ref"].upper() for p in self.data["components"]}: raise ValueError("Unknown probe component")
        self.commit(lambda d: d["probes"].append({"id": uuid.uuid4().hex, "expression": expression, "anchor": anchor, "descriptor": probe.to_dict()}))

    def bom(self):
        groups = {}
        for part in self.data["components"]:
            key = (part["kind"], part["value"], part["package"], part["variant"])
            groups.setdefault(key, []).append(part["ref"])
        return [{"refs": ", ".join(refs), "quantity": len(refs), "kind": k[0], "value": k[1], "package": k[2], "variant": k[3]} for k, refs in sorted(groups.items())]


COMMANDS = {"file.open": "Ctrl+O", "file.save": "Ctrl+S", "file.import": "Ctrl+I", "file.export": "Ctrl+Shift+E",
    "edit.undo": "Ctrl+Z", "edit.redo": "Ctrl+Y", "edit.paste": "Ctrl+V", "edit.properties": "E",
    "probe.voltage": "P", "probe.differential": "Shift+P", "probe.current": "I", "probe.power": "Shift+I",
    "view.fit": "Home", "run.start": "F5", "view.parts": "A", "view.math": "Ctrl+M", "view.ide": "Ctrl+K", "help.open": "F1"}
COMMANDS.update({'file.new': 'Ctrl+N', 'run.interactive': 'Ctrl+F5',
                 'run.pause': 'F6', 'run.stop': 'Shift+F5'})
COMMANDS.update({'run.manager':'Ctrl+J','run.thermal_setup':'Ctrl+Shift+T'})
COMMANDS.update({'view.directives':'Ctrl+D','edit.directive':'S'})
COMMANDS.update({'view.frequency':'Ctrl+Shift+F'})
COMMANDS.update({'view.power_tree':'Ctrl+Shift+P','view.analytics':'Ctrl+Shift+A'})
COMMANDS.update({'part.resistor':'R','part.capacitor':'C','part.inductor':'L','part.diode':'D'})
COMMANDS.update({'edit.rotate':'Space','edit.wire':'W'})
COMMANDS.update({'view.command_search':'Ctrl+Shift+K'})
COMMANDS.update({'edit.copy':'Ctrl+C','edit.select_all':'Ctrl+A',
                 'edit.properties_standard':'Ctrl+E','edit.rotate_standard':'Ctrl+R',
                 'edit.redo_alternative':'Ctrl+Shift+Z','view.schematic':'Ctrl+1',
                 'view.plots':'Ctrl+2','view.circuit_text':'Ctrl+3'})


class Keymap:
    def __init__(self, bindings=None, part_shortcuts=True):
        self.bindings = dict(COMMANDS if bindings is None else bindings)
        if not isinstance(part_shortcuts,bool):raise ValueError('part_shortcuts must be boolean')
        self.part_shortcuts=part_shortcuts
        self.validate()

    def validate(self):
        import re
        if any(k not in COMMANDS and not re.fullmatch(r'part:generic\.[a-z_]+\.\d{3}',k) for k in self.bindings):raise ValueError("Unknown shortcut command; link a preset with part:generic.family.001")
        seen = set()
        for value in self.bindings.values():
            if not isinstance(value,str):raise ValueError('Shortcut must be text')
            normalized = value.lower().replace(" ", "")
            if normalized in seen: raise ValueError(f"Shortcut conflict: {value}")
            seen.add(normalized)
            if not value or len(value) > 48: raise ValueError("Invalid shortcut")

    @classmethod
    def preset(cls, name):
        if name not in ("SPIKES", "KiCad-inspired", "LTspice-inspired"): raise ValueError("Unknown profile")
        bindings = dict(COMMANDS)
        if name == "LTspice-inspired":
            bindings.update({"view.parts": "F2", "run.start": "Ctrl+R", "edit.properties": "Ctrl+P",'edit.rotate_standard':'Ctrl+Shift+R'})
        return cls(bindings)

    def save(self, path):
        self.validate()
        write_json(path,self.to_data())

    def to_data(self):return {'contract':'spikes/shortcuts/v2','bindings':self.bindings,'part_shortcuts':self.part_shortcuts}

    @classmethod
    def from_data(cls,data):
        if not isinstance(data,dict):raise ValueError('Shortcut profile must be an object')
        if 'contract' not in data:return cls(data)
        if data.get('contract') not in ('spikes/shortcuts/v1','spikes/shortcuts/v2'):raise ValueError('Unsupported shortcut version')
        return cls(data['bindings'],data.get('part_shortcuts',True))

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_data(data)
