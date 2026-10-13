# SPDX-License-Identifier: Apache-2.0
"""Extract a copied KiCad board's native filled copper into neutral polygons.

Run with the installed KiCad Python interpreter. This is a development evidence
adapter, not an importer or manufacturing-geometry qualification. Native curves
are polygonized at the explicitly recorded maximum chord error.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pcbnew


def polygons(poly):
    poly.Unfracture()
    def ring(chain):
        return [[pcbnew.ToMM(chain.CPoint(i).x), pcbnew.ToMM(chain.CPoint(i).y)]
                for i in range(chain.PointCount())]
    return [{'outer_mm': ring(poly.Outline(i)),
             'holes_mm': [ring(poly.Hole(i, j)) for j in range(poly.HoleCount(i))]}
            for i in range(poly.OutlineCount())]


def prepare_candidate(source, output, chord_error_mm):
    output.mkdir(parents=True, exist_ok=False)
    original = source.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    candidate = output / source.name
    candidate.write_bytes(original)
    # The UNO conversion duplicated identical Edge.Cuts items. Removing an
    # exact geometric duplicate changes no physical boundary or routing.
    board = pcbnew.LoadBoard(str(candidate.resolve()))
    if board is None:
        raise ValueError('Native source load failed; repair undefined source layers first')
    seen, removed = set(), []
    for drawing in list(board.GetDrawings()):
        if drawing.GetLayer() != pcbnew.Edge_Cuts or not isinstance(drawing, pcbnew.PCB_SHAPE):
            continue
        def point(p):
            return (p.x, p.y)
        endpoints = tuple(sorted((point(drawing.GetStart()), point(drawing.GetEnd()))))
        shape = drawing.GetShape()
        middle = point(drawing.GetArcMid()) if shape == pcbnew.SHAPE_T_ARC else None
        key = (shape, endpoints, middle)
        if key in seen:
            removed.append(drawing.m_Uuid.AsString())
            board.Remove(drawing)
        seen.add(key)
    pcbnew.SaveBoard(str(candidate.resolve()), board)
    command = [str(Path(sys.executable).with_name('kicad-cli.exe')), 'pcb', 'drc',
               '--refill-zones', '--save-board', '--format', 'json',
               '--output', str((output/'drc.json').resolve()), str(candidate.resolve())]
    native = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (output/'native-drc.log').write_text(native.stdout+'\n'+native.stderr, encoding='utf-8')
    if native.returncode:
        raise ValueError('Native refill/DRC failed; inspect native-drc.log')
    (output/'repair.json').write_text(json.dumps({'source_sha256':before,
        'removed_outline_duplicates':removed}),encoding='utf-8')
    subprocess.run([sys.executable,str(Path(__file__).resolve()),'--source',str(source.resolve()),
        '--output',str(output.resolve()),'--chord-error-mm',str(chord_error_mm),'--extract-only'],check=True,
        timeout=180)


def extract(source, output, chord_error_mm):
    receipt=json.loads((output/'repair.json').read_text(encoding='utf-8'))
    before=receipt['source_sha256']; removed=receipt['removed_outline_duplicates']
    candidate=output/source.name
    board = pcbnew.LoadBoard(str(candidate.resolve()))
    error = pcbnew.FromMM(chord_error_mm)
    copper_layers = list(board.GetEnabledLayers().CuStack())
    outlines = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outlines, False):
        raise ValueError('Native board outline extraction failed; inferred bounds are forbidden')
    copper, drills, pads = [], [], []

    def emit(item, layer, kind, reference=''):
        poly = pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(poly, layer, 0, error, pcbnew.ERROR_INSIDE)
        rows = polygons(poly)
        if not rows:
            raise ValueError('Empty native copper shape: '+item.m_Uuid.AsString())
        copper.append({'id': item.m_Uuid.AsString()+':'+pcbnew.LayerName(layer),
                       'source_id': item.m_Uuid.AsString(), 'kind': kind,
                       'net': item.GetNetname() if hasattr(item, 'GetNetname') else '',
                       'layer': pcbnew.LayerName(layer), 'polygons': rows,
                       'reference': reference})

    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            layers = [l for l in copper_layers if item.IsOnLayer(l)]
            for layer in layers:
                emit(item, layer, 'via_land')
            drills.append({'id': item.m_Uuid.AsString(), 'kind': 'via',
                'net': item.GetNetname(), 'center_mm': [pcbnew.ToMM(item.GetPosition().x), pcbnew.ToMM(item.GetPosition().y)],
                'diameter_mm': pcbnew.ToMM(item.GetDrillValue()), 'plated': True,
                'start_layer': pcbnew.LayerName(layers[0]), 'end_layer': pcbnew.LayerName(layers[-1])})
        else:
            emit(item, item.GetLayer(), 'track')
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            layers = [l for l in copper_layers if pad.IsOnLayer(l)]
            # An NPTH mechanical pad is a drill void, even when KiCad lists
            # wildcard copper layers for its clearance semantics.
            for layer in ([] if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else layers):
                emit(pad, layer, 'pad', footprint.GetReference()+'.'+pad.GetNumber())
            xy = [pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)]
            pads.append({'id': pad.m_Uuid.AsString(), 'reference': footprint.GetReference(),
                         'number': pad.GetNumber(), 'net': pad.GetNetname(), 'center_mm': xy})
            drill = pad.GetDrillSize()
            if drill.x or drill.y:
                poly = pcbnew.SHAPE_POLY_SET()
                pad.GetEffectiveHoleShape().TransformToPolygon(poly, error, pcbnew.ERROR_INSIDE)
                drills.append({'id': pad.m_Uuid.AsString(), 'kind': 'pad', 'net': pad.GetNetname(),
                    'center_mm': xy, 'polygons': polygons(poly),
                    'plated': pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                    'start_layer': pcbnew.LayerName(copper_layers[0]),
                    'end_layer': pcbnew.LayerName(copper_layers[-1])})
        for item in footprint.GraphicalItems():
            if item.GetLayer() in copper_layers:
                emit(item, item.GetLayer(), 'footprint_graphic', footprint.GetReference())
    for item in board.GetDrawings():
        if item.GetLayer() in copper_layers:
            emit(item, item.GetLayer(), 'board_graphic')
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        for layer in zone.GetLayerSet().CuStack():
            rows = polygons(zone.GetFilledPolysList(layer))
            copper.append({'id': zone.m_Uuid.AsString()+':'+pcbnew.LayerName(layer),
                'source_id': zone.m_Uuid.AsString(), 'kind': 'filled_zone',
                'net': zone.GetNetname(), 'layer': pcbnew.LayerName(layer), 'polygons': rows})
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError('Original source changed during extraction')
    result = {'contract': 'spike/routed-board-polygons/v1', 'units': 'mm',
        'source_sha256': before, 'filled_source_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
        'removed_exact_outline_duplicates': removed,
        'kicad_version': pcbnew.GetBuildVersion(), 'chord_error_mm': chord_error_mm,
        'board': polygons(outlines), 'layers': [pcbnew.LayerName(l) for l in copper_layers],
        'declared_board_thickness_mm': pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness()),
        'copper': copper, 'drills': drills, 'pads': pads,
        'limitations': ['Native polygonized curves use ERROR_INSIDE, bounded by the declared chord error.',
                       'Refilled converted source is a study derivative, not manufacturer Gerber verification.',
                       'Stack dielectric properties, plating and connector solids are not inferred.']}
    (output/'polygons.json').write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'source':str(source), 'copper_objects':len(copper), 'drills':len(drills),
                      'pads':len(pads), 'board_polygons':len(result['board'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chord-error-mm', type=float, default=.01)
    parser.add_argument('--extract-only', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1e-5 <= args.chord_error_mm <= .05:
        parser.error('chord error must be between 1e-5 and .05 mm')
    (extract if args.extract_only else prepare_candidate)(args.source,args.output,args.chord_error_mm)
