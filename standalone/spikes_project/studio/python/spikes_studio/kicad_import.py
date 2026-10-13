# SPDX-License-Identifier: Apache-2.0
"""Native KiCad connectivity export with explicit drawing/model loss reports."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
from .document import Document
from .interchange import ImportReport, sexpr
from .schematic_layout import source_routes


def children(tree, tag):
    return [row for row in tree if isinstance(row, list) and row and row[0] == tag]


def field(tree, tag, default=''):
    rows = children(tree, tag)
    return rows[0][1] if rows and len(rows[0]) > 1 else default


def inventory(text):
    tree = sexpr(text)
    result = []
    for symbol in children(tree, 'symbol'):
        props = {row[1]: row[2] for row in children(symbol, 'property') if len(row) >= 3}
        at = children(symbol, 'at')
        result.append(dict(reference=props.get('Reference', ''), value=props.get('Value', ''),
                           properties=props, at=at[0][1:3] if at else None))
    return result


def executable():
    explicit = os.environ.get('SPIKES_KICAD_CLI')
    if explicit:
        path = Path(explicit)
        if not path.is_file(): raise ValueError('SPIKES_KICAD_CLI does not name a file')
        return path
    found = shutil.which('kicad-cli')
    if found: return Path(found)
    candidates = sorted(Path('C:/Program Files/KiCad').glob('*/bin/kicad-cli.exe'))
    if candidates: return candidates[-1]
    raise ValueError('Install KiCad or set SPIKES_KICAD_CLI to enable native schematic import')


def normalize_native_nodes(deck, connectivity):
    """Rename only exporter-declared nets; preserve paths and the alias map."""
    tree=sexpr(connectivity);groups=children(tree,'nets');mapping={}
    if not groups:raise ValueError('Native KiCad export contains no connectivity table')
    for net in children(groups[0],'net'):
        name=str(field(net,'name'));code=str(field(net,'code'))
        if name.upper() in ('GND','0','/GND'):
            mapping[name]='0'
            # KiCad's SPICE exporter emits GND for the /GND net in its
            # connectivity export; bind that observed alias explicitly.
            if name.upper()=='/GND':mapping['GND']='0'
        elif not re.fullmatch(r'[A-Za-z0-9_.$+-]+',name):mapping[name]='kicad_net_'+code
    if not mapping:return deck,{}
    names=sorted(mapping,key=len,reverse=True)
    pattern=re.compile(r'(?<![A-Za-z0-9_.$:/+-])(?:'+'|'.join(re.escape(n) for n in names)+r')(?![A-Za-z0-9_.$:/+-])')
    lines=[]
    for line in deck.splitlines():
        if line.lstrip().lower().startswith(('.include ','.lib ','.title ','*')):
            lines.append(line);continue
        pieces=re.split(r'("(?:\\.|[^"\\])*")',line)
        for index in range(0,len(pieces),2):pieces[index]=pattern.sub(lambda match:mapping[match.group()],pieces[index])
        lines.append(''.join(pieces))
    return '\n'.join(lines)+'\n',mapping


def import_schematic(path, cli=None):
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != '.kicad_sch': raise ValueError('Expected a .kicad_sch file')
    if path.stat().st_size > 16 * 1024 * 1024: raise ValueError('KiCad schematic exceeds 16 MiB')
    original = path.read_text(encoding='utf-8-sig')
    records = inventory(original)
    with tempfile.TemporaryDirectory(prefix='spikes-kicad-') as temporary:
        output = Path(temporary) / 'export.cir'
        result = subprocess.run([str(cli or executable()), 'sch', 'export', 'netlist',
            '--format', 'spice', '--output', str(output), str(path)], cwd=str(path.parent),
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode or not output.is_file():
            raise ValueError('KiCad netlist export failed: ' + (result.stderr or result.stdout)[-2000:])
        if output.stat().st_size > 8 * 1024 * 1024: raise ValueError('Exported SPICE deck exceeds 8 MiB')
        deck = output.read_text(encoding='utf-8-sig')
        connectivity=Path(temporary)/'connectivity.net'
        nets_result=subprocess.run([str(cli or executable()),'sch','export','netlist',
            '--format','kicadsexpr','--output',str(connectivity),str(path)],cwd=str(path.parent),
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if nets_result.returncode or not connectivity.is_file():raise ValueError('KiCad connectivity export failed')
        if connectivity.stat().st_size>16*1024*1024:raise ValueError('KiCad connectivity exceeds 16 MiB')
        deck,aliases=normalize_native_nodes(deck,connectivity.read_text(encoding='utf-8-sig'))
    warnings = ['Connectivity comes from native KiCad SPICE export. Studio normalizes symbols '
                'and redraws routes; original wires, sheet graphics and library glyphs are not round-tripped.']
    if result.stderr.strip(): warnings.append('KiCad: ' + result.stderr.strip()[-2000:])
    if not re.search(r'(?im)^\s*\.(?:op|dc|ac|tran|noise|tf|pz|sens|disto)\b',deck):
        deck=re.sub(r'(?im)^\s*\.end\s*$', '.op\n.end',deck)
        warnings.append('No analysis was exported. Added an explicit .op setup for review; use Simulation manager to select transient or another analysis. No excitation was invented.')
    try:
        document = Document.from_netlist(deck)
    except (ValueError, RuntimeError) as error:
        return ImportReport('kicad', original, None, records,
                            warnings + ['Exported deck needs model/analysis mapping: ' + str(error),
                                        'No incomplete circuit was substituted or executed.'])
    positions = {row['reference'].upper(): row['at'] for row in records if row['at']}
    if positions:
        xs = [float(at[0]) for at in positions.values()]; ys = [float(at[1]) for at in positions.values()]
        for part in document.data['components']:
            at = positions.get(part['ref'].upper())
            if at:
                part['x'] = round((float(at[0])-min(xs))*8/10)*10 + 140
                part['y'] = round((float(at[1])-min(ys))*8/10)*10 + 180
    document.data['metadata']['kicad_import'] = dict(path=str(path), warnings=warnings, inventory=records,
                                                   net_aliases=aliases,original_source=original)
    source_routes(document)
    return ImportReport('kicad', original, document, records, warnings)


def import_generic_netlist(text):
    tree = sexpr(text)
    components = children(tree, 'components'); nets = children(tree, 'nets')
    if not components or not nets: raise ValueError('KiCad netlist requires components and nets')
    parts = children(components[0], 'comp'); mapping = {}; aliases = {}; records = []
    for net in children(nets[0], 'net'):
        code = str(field(net, 'code')); name = str(field(net, 'name'))
        node = '0' if name.upper() in ('GND', '0', '/GND') else 'k' + code
        aliases[node] = name
        for terminal in children(net, 'node'):
            key = (str(field(terminal, 'ref')), str(field(terminal, 'pin')))
            if key in mapping: raise ValueError('Pin assigned to multiple nets: ' + str(key))
            mapping[key] = node
    lines = ['* KiCad passive netlist import']; unsupported = []
    for part in parts:
        ref = str(field(part, 'ref')); value = str(field(part, 'value'))
        records.append(dict(reference=ref, value=value))
        pins = {pin for component, pin in mapping if component == ref}
        if not ref or ref[0].upper() not in 'RCL' or pins != {'1', '2'}:
            unsupported.append(ref);continue
        if any(ch.isspace() for ch in value + ref): unsupported.append(ref);continue
        lines.append(f'{ref} {mapping[ref,"1"]} {mapping[ref,"2"]} {value}')
    if unsupported:
        return ImportReport('kicad_netlist', text, None, records,
            ['Model/pin mapping required for: ' + ', '.join(unsupported), 'No partial simulation circuit was created.'])
    if not parts: raise ValueError('KiCad netlist contains no components')
    lines.extend(['.op', '.end'])
    document = Document.from_netlist('\n'.join(lines)+'\n')
    document.data['metadata']['kicad_import'] = dict(net_aliases=aliases, original_source=text)
    source_routes(document)
    return ImportReport('kicad_netlist', text, document, records,
        ['R/C/L pin mappings imported. No excitation was invented; select an analysis and add sources before transient testing.'])
