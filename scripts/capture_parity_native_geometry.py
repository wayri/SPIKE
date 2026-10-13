# SPDX-License-Identifier: Apache-2.0
"""Capture public native KiCad facts and an optional bounded ODB export."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pose_source(base: str, token: str, side: str, footprint_angle: int, pad_angle: int | None) -> str:
    for literal in ('(footprint "Parity:RotatedPad" (layer "F.Cu")', '(at 20 10 90)', '(at 2 1 0)'):
        if base.count(literal) != 1:
            raise ValueError('Native pose cohort requires the unchanged original placement source.')
    text = base.replace('(footprint "Parity:RotatedPad" (layer "F.Cu")',
                        f'({token} "Parity:RotatedPad" (layer "{side}")')
    text = text.replace('(at 20 10 90)', f'(at 20 10 {footprint_angle})')
    text = text.replace('(at 2 1 0)', '(at 2 1' + (')' if pad_angle is None else f' {pad_angle})'))
    return text.replace('(layers "F.Cu")', f'(layers "{side}")')


def shape_source(base: str, side: str, angle: int, kind: str) -> str:
    old_pad = '(pad "1" smd rect (at 2 1 0) (size 1.2 0.8) (layers "F.Cu") (net 1 "SIGNAL")\n      (uuid "66666666-6666-4666-8666-666666666666"))'
    if old_pad not in base:
        raise ValueError('Native shape cohort requires the unchanged original pad source.')
    if kind == 'slot':
        pad = f'(pad "1" thru_hole oval (at 2 1 {angle}) (size 2 1) (drill oval 1.2 .4) (layers "*.Cu" "*.Mask") (net 1 "SIGNAL"))'
    elif kind == 'custom':
        pad = f'(pad "1" smd custom (at 2 1 {angle}) (size .2 .2) (layers "{side}") (net 1 "SIGNAL") (options (clearance outline) (anchor rect)) (primitives (gr_poly (pts (xy -.1 -.1) (xy 2 -.1) (xy 2 .5) (xy -.1 .5)) (width 0) (fill yes))))'
    else:
        raise ValueError('Unknown native shape case.')
    return base.replace(old_pad, pad).replace('(footprint "Parity:RotatedPad" (layer "F.Cu")', f'(footprint "Parity:RotatedPad" (layer "{side}")')


def capture(source: Path, output: Path, scratch: Path, export: Path | None, archive: Path | None) -> None:
    import pcbnew  # Run with the installed native KiCad interpreter.
    def point(p): return [pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)]
    def bbox(box): return [pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY()),
                           pcbnew.ToMM(box.GetWidth()), pcbnew.ToMM(box.GetHeight())]
    def pad_facts(p):
        return {'source_id': p.m_Uuid.AsString(), 'center_mm': point(p.GetPosition()),
                'size_mm': point(p.GetSize()), 'native_angle_deg': p.GetOrientationDegrees(),
                'bbox_mm': bbox(p.GetBoundingBox())}
    board = pcbnew.LoadBoard(str(source.resolve()))
    polygons = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(polygons, False):
        raise ValueError('Native source outline could not be read without inference.')
    facts = {'contract': 'spike/native-kicad-geometry/v1', 'kicad_version': pcbnew.GetBuildVersion(),
             'source_sha256': digest(source), 'runner_sha256': digest(Path(__file__)),
             'pads': [pad_facts(p) for p in board.GetPads()],
             'components': [{'reference': f.GetReference(), 'position_mm': point(f.GetPosition()),
                             'native_angle_deg': f.GetOrientationDegrees()} for f in board.GetFootprints()],
             'arcs': [{'start_mm': point(a.GetStart()), 'mid_mm': point(a.GetMid()),
                       'end_mm': point(a.GetEnd()), 'width_mm': pcbnew.ToMM(a.GetWidth()),
                       'net': a.GetNetname(), 'layer': board.GetLayerName(a.GetLayer())}
                      for a in board.GetTracks() if isinstance(a, pcbnew.PCB_ARC)],
             'outline': {'area_mm2': polygons.Area() / 1e12, 'outer_count': polygons.OutlineCount(),
                         'cutout_count': sum(polygons.HoleCount(i) for i in range(polygons.OutlineCount()))},
             'pad_cases': [], 'shape_cases': []}
    scratch.mkdir(parents=True, exist_ok=True)
    base = source.read_text(encoding='utf-8')
    for token in ('footprint', 'module'):
        for side in ('F.Cu', 'B.Cu'):
            for footprint_angle in (0, 90, 37):
                for pad_angle in (None, 0, 23, 90):
                    text = pose_source(base, token, side, footprint_angle, pad_angle)
                    path = scratch / f'{token}-{side}-{footprint_angle}-{pad_angle}.kicad_pcb'
                    path.write_text(text, encoding='utf-8', newline='\n')
                    native = pcbnew.LoadBoard(str(path.resolve()))
                    row = {'token': token, 'side': side, 'footprint_angle': footprint_angle,
                           'pad_angle': pad_angle, 'source_sha256': digest(path),
                           'native_footprint_angle_deg': list(native.GetFootprints())[0].GetOrientationDegrees(),
                           **pad_facts(list(native.GetPads())[0])}
                    facts['pad_cases'].append(row)
    for side in ('F.Cu', 'B.Cu'):
        for angle in (0, 90):
            for kind in ('slot', 'custom'):
                text = shape_source(base, side, angle, kind)
                path = scratch / f'{kind}-{side}-{angle}.kicad_pcb'
                path.write_text(text, encoding='utf-8', newline='\n')
                native = pcbnew.LoadBoard(str(path.resolve()))
                obj = list(native.GetPads())[0]
                row = {'kind': kind, 'side': side, 'pad_angle': angle, 'source_sha256': digest(path), **pad_facts(obj)}
                if kind == 'slot': row['hole_bbox_mm'] = bbox(obj.GetEffectiveHoleShape().BBox())
                facts['shape_cases'].append(row)
    if export is not None:
        if export.exists() or archive is None or archive.exists():
            raise ValueError('Select fresh native export and archive paths.')
        pcbnew.PCB_IO_MGR.Save(pcbnew.PCB_IO_MGR.ODBPP, str(export.resolve()), board, pcbnew.str_utf8_Map())
        members = []
        omitted = []
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_STORED) as package:
            for path in sorted(p for p in export.rglob('*') if p.is_file()):
                name = path.relative_to(export).as_posix()
                record = {'name': name, 'sha256': digest(path), 'size_bytes': path.stat().st_size}
                if name.startswith('fonts/'):
                    omitted.append({**record, 'reason': 'Generated font excluded from redistributed geometry-only fixture.'})
                    continue
                info = zipfile.ZipInfo('job/' + name, (1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                package.writestr(info, path.read_bytes())
                members.append(record)
        facts['native_export'] = {'method': 'PCB_IO_MGR.Save(ODBPP, absolute path, BOARD, str_utf8_Map())',
                                  'archive_sha256': digest(archive), 'members': members, 'omitted': omitted}
    output.write_text(json.dumps(facts, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Native facts captured: {len(facts["pad_cases"])} poses and {len(facts["shape_cases"])} shape cases.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--export', type=Path)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    capture(args.source, args.output, args.scratch, args.export, args.archive)
