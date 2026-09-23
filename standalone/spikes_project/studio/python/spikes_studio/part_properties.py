"""Editable model forms whose accepted fields compile to real SPICE records."""
import re


OPTIONS = {
    'resistor': [('ideal','Ideal resistor')],
    'capacitor': [('ideal','Ideal capacitor')],
    'inductor': [('ideal','Ideal inductor')],
    'voltage_source': [('dc','DC voltage'),('pulse','PULSE voltage'),('pwl','PWL voltage')],
    'current_source': [('dc','DC current'),('pulse','PULSE current'),('pwl','PWL current')],
    'diode': [('named_model','Existing .MODEL D'),('shockley','Custom Shockley diode')],
    'voltage_controlled_switch': [('smooth_switch','Smooth voltage-controlled switch')],
}
VALUE_LABELS = {'resistor':'Resistance [ohm]', 'capacitor':'Capacitance [F]',
                'inductor':'Inductance [H]', 'voltage_source':'DC / initial voltage [V]',
                'current_source':'DC / initial current [A]', 'diode':'Model-defined value',
                'voltage_controlled_switch':'Model-defined resistance'}
FIELDS = {
    'dc':[('ac_magnitude','AC magnitude [V or A]','0'),('ac_phase','AC phase [deg]','0')],
    'pulse':[('high','Pulsed level [V or A]','1'),('delay','Delay [s]','0'),
             ('rise','Rise time [s]','1u'),('fall','Fall time [s]','1u'),
             ('width','Pulse width [s]','500u'),('period','Period [s]','1m')],
    'pwl':[('points','Time / value pairs (one pair per line; seconds, V or A)','0 0\n1m 1')],
    'named_model':[('model_name','Diode model name','')],
    'shockley':[('is','Saturation current IS [A]','10f'),('n','Emission coefficient N','1'),
                ('tnom','TNOM [°C] (card metadata; .TEMP sets actual temperature)','27'),
                ('kf','Flicker coefficient KF (noise analysis only)','0'),('af','Flicker exponent AF','1')],
    'smooth_switch':[('ron','On resistance [ohm]','1m'),('roff','Off resistance [ohm]','1G'),
                     ('vt','Threshold [V]','.5'),('transition','Smooth transition width [V]','1m')],
}


def parse(source):
    from python.spikes.netlist import parse_netlist
    return parse_netlist(source,native_extensions=True,transient_capture='rolling')


def form(source,ref,project=None):
    project=project or parse(source)
    element=next((e for e in project.elements if e.name.upper()==ref.upper()),None)
    if element is None:raise ValueError(f'Unknown component {ref}')
    number=lambda x:format(x,'.12g')
    kind=element.kind
    result={'kind':kind,'mode':'ideal','value':number(element.value),'fields':{},
            'options':OPTIONS.get(kind,[]),'editable':kind in OPTIONS and ':' not in ref,
            'nodes':[]}
    from .pin_geometry import ordered_nodes
    result['nodes']=ordered_nodes(element)
    if kind in ('capacitor','inductor'):
        result['fields']['ic']=number(element.initial_condition)
    if kind in ('voltage_source','current_source'):
        waveform=element.waveform
        result['mode']=waveform.kind if waveform else 'dc'
        result['fields']={'ac_magnitude':number(element.ac_magnitude),'ac_phase':number(element.ac_phase_deg)}
        if waveform and waveform.kind=='pulse':
            result['fields'].update(zip(('high','delay','rise','fall','width','period'),map(number,waveform.pulse[1:])))
        elif waveform:
            result['fields']['points']='\n'.join(f'{number(t)} {number(v)}' for t,v in waveform.points)
    if kind=='diode':
        model=element.diode_model
        result['mode']='shockley' if element.model_name.startswith('SPIKES_'+ref.upper()) else 'named_model'
        result['fields']={'model_name':element.model_name,'is':number(model.saturation_current_a),
                          'n':number(model.emission_coefficient),'tnom':number(model.temperature_k-273.15),
                          'kf':number(model.flicker_noise_coefficient),'af':number(model.flicker_noise_exponent)}
        logical=re.sub(r'\n[ \t]*\+[ \t]*',' ',source)
        card=re.search(r'(?im)^\s*\.model\s+'+re.escape(element.model_name)+r'\s+D\s*\(([^\n]*)\)',logical)
        if card:
            tnom=re.search(r'(?i)\bTNOM\s*=\s*([^\s,)]+)',card[1])
            if tnom:result['fields']['tnom']=tnom[1]
    if kind=='voltage_controlled_switch':
        model=element.switch_model;result['mode']='smooth_switch'
        result['fields']=dict(zip(('ron','roff','vt','transition'),map(number,(model.on_resistance_ohm,
            model.off_resistance_ohm,model.threshold_voltage_v,model.transition_voltage_v))))
    if element.behavioral_expression is not None:result['editable']=False;result['options']=[]
    # Keep parameter expressions/suffixes for fields the user did not change.
    # Elaborated numeric values alone would silently freeze .param bindings.
    from python.spikes.netlist import _tokens,_content
    logical=re.sub(r'\n[ \t]*\+[ \t]*',' ',source)
    records=[_tokens(_content(line)) for line in logical.splitlines()[1:] if _content(line)]
    record=next((t for t in records if t and t[0].upper()==ref.upper()),None)
    if record and ':' not in ref:
        if kind in ('resistor','capacitor','inductor'):
            result['value']=record[3]
            if len(record)>4 and record[4].upper().startswith('IC='):result['fields']['ic']=record[4][3:]
        elif kind in ('voltage_source','current_source'):
            tail=record[3:]
            if result['mode']=='dc':
                if tail and tail[0].upper()=='DC':result['value']=tail[1]
                elif tail and tail[0].upper()!='AC':result['value']=tail[0]
                if 'AC' in [t.upper() for t in tail]:
                    index=[t.upper() for t in tail].index('AC')
                    result['fields']['ac_magnitude']=tail[index+1]
                    if index+2<len(tail) and tail[index+2].upper()!='DC':result['fields']['ac_phase']=tail[index+2]
            else:
                matched=re.fullmatch(r'(?is)(?:PULSE|PWL)\s*\((.*)\)',' '.join(tail))
                if matched:
                    values=_tokens(matched[1].replace(',',' '))
                    if result['mode']=='pulse' and len(values)==7:
                        result['value']=values[0];result['fields'].update(zip(('high','delay','rise','fall','width','period'),values[1:]))
                    elif result['mode']=='pwl':result['fields']['points']='\n'.join(' '.join(values[i:i+2]) for i in range(0,len(values),2))
        elif kind=='voltage_controlled_switch':result['fields'].update(zip(('ron','roff','vt','transition'),record[5:9]))
    return result


def field_specs(kind,mode):
    if mode=='ideal':
        return [('ic','Initial capacitor voltage [V]' if kind=='capacitor' else 'Initial inductor current [A]','0')] if kind in ('capacitor','inductor') else []
    return FIELDS.get(mode,[])


def model_names(source):
    return sorted({e.model_name for e in parse(source).elements if e.model_name} |
                  {m[1].upper() for m in re.finditer(r'(?im)^\s*\.model\s+([\w.$+-]+)\s+D\b',source)})


def rewrite_nodes(source, ref, nodes):
    """Edit only top-level terminal tokens; retain models, expressions and suffixes.

    This does not claim arbitrary hierarchical net renaming. Included/elaborated
    records must still be edited at their definition.
    """
    from .pin_geometry import ordered_nodes
    project=parse(source)
    element=next((e for e in project.elements if e.name.upper()==ref.upper()),None)
    if element is None or ':' in ref:raise ValueError('Edit hierarchical pins at their definition')
    if not isinstance(nodes,list) or len(nodes)!=len(ordered_nodes(element)):
        raise ValueError('Incorrect ordered terminal count')
    if not all(isinstance(n,str) and re.fullmatch(r'[A-Za-z0-9_.$+-]+',n) for n in nodes):
        raise ValueError('Pins require single SPICE node names')
    physical=list(nodes)
    if element.semiconductor_nodes:physical=[nodes[0],nodes[2],nodes[1],*nodes[3:]]
    lines=source.splitlines(keepends=True);depth=0;matches=[]
    for i,line in enumerate(lines):
        tokens=line.split()
        if not tokens:continue
        if tokens[0].lower()=='.subckt':depth+=1
        elif tokens[0].lower()=='.ends':depth-=1
        elif i>0 and depth==0 and tokens[0].upper()==ref.upper():matches.append(i)
    if len(matches)!=1:raise ValueError('No unique top-level instance to rewire')
    i=matches[0];spans=list(re.finditer(r'\S+',lines[i]))
    if len(spans)<1+len(physical):raise ValueError('Terminal continuation requires explicit source editing')
    for span,node in reversed(list(zip(spans[1:1+len(physical)],physical))):
        lines[i]=lines[i][:span.start()]+node+lines[i][span.end():]
    candidate=''.join(lines);parse(candidate)
    return candidate


def rewrite(source,ref,changes,model=None):
    """Rewrite exactly one top-level instance; never mutate a shared model card.

    A custom diode gets a fresh per-instance card. Parser validation happens
    before returning, so unknown fields or invalid values cannot enter a deck.
    """
    if model is None and 'nodes' in changes and 'value' not in changes:return rewrite_nodes(source,ref,changes['nodes'])
    current=form(source,ref)
    if not current['editable']:raise ValueError('This device or hierarchical instance requires the Circuit text editor')
    mode=(model or {}).get('mode',current['mode'])
    if mode not in dict(current['options']):raise ValueError(f'{mode} is not a model type for {current["kind"]}')
    supplied=(model or {}).get('fields',{})
    specs=field_specs(current['kind'],mode)
    if set(supplied)-{key for key,_,_ in specs}:raise ValueError('Unknown model field')
    fields={key:current['fields'].get(key,default) for key,_,default in specs}
    fields.update(supplied)
    value=changes.get('value',current['value'])
    nodes=changes.get('nodes',current['nodes'])
    if not isinstance(nodes,list) or len(nodes)!=len(current['nodes']):raise ValueError(f'Expected {len(current["nodes"])} ordered nodes')
    if not all(isinstance(n,str) and re.fullmatch(r'[A-Za-z0-9_.$+-]+',n) for n in nodes):raise ValueError('Pins require single SPICE node names')
    def scalar(text):
        text=str(text).strip()
        if not text or any(c in text for c in '\r\n;'):raise ValueError('Enter one SPICE value, e.g. 4.7k, 220u, or {parameter}')
        return text
    prefix=' '.join([ref,*nodes]);addition=None
    if mode=='ideal':
        line=f'{prefix} {scalar(value)}'
        if fields:line+=f' IC={scalar(fields["ic"])}'
    elif mode=='dc':
        line=f'{prefix} DC {scalar(value)} AC {scalar(fields["ac_magnitude"])} {scalar(fields["ac_phase"])}'
    elif mode=='pulse':
        line=f'{prefix} PULSE('+ ' '.join(map(scalar,[value,*[fields[key] for key,_,_ in specs]]))+')'
    elif mode=='pwl':
        points=' '.join(fields['points'].split())
        if not points or any(c in points for c in ';()'):raise ValueError('Enter time/value pairs, e.g. 0 0 followed by 1m 5')
        line=f'{prefix} PWL({points})'
    elif mode=='named_model':
        name=scalar(fields['model_name']).upper()
        if name not in model_names(source):raise ValueError(f'No existing diode model named {name}; choose Custom Shockley or add a .MODEL D card')
        line=f'{prefix} {name}'
    elif mode=='shockley':
        names=model_names(source);base='SPIKES_'+ref.upper();name=base;index=1
        while name in names:name=f'{base}_{index}';index+=1
        addition=f'.model {name} D('+ ' '.join(f'{key.upper()}={scalar(fields[key])}' for key,_,_ in specs)+')'
        line=f'{prefix} {name}'
    else:
        line=prefix+' '+' '.join(scalar(fields[key]) for key,_,_ in specs)
    lines=source.splitlines();matches=[];depth=0
    for i,text in enumerate(lines):
        tokens=text.split()
        if not tokens:continue
        if tokens[0].lower()=='.subckt':depth+=1
        if tokens[0].lower()=='.ends':depth-=1
        if i>0 and depth==0 and tokens[0].upper()==ref.upper():matches.append(i)
    if len(matches)!=1:raise ValueError('Edit included/hierarchical source at its definition; no unique top-level instance found')
    start=matches[0];end=start+1
    while end<len(lines) and lines[end].lstrip().startswith('+'):end+=1
    lines[start:end]=[line]
    if addition:
        endline=next((i for i,text in enumerate(lines) if text.strip().lower()=='.end'),len(lines))
        lines.insert(endline,addition)
    candidate='\n'.join(lines)+'\n';parse(candidate)
    return candidate
