# SPDX-License-Identifier: Apache-2.0
"""Prepare original black-box STEP placement boards through public pcbnew API."""
import argparse
import json
from pathlib import Path
import pcbnew

p = argparse.ArgumentParser()
p.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[2])
p.add_argument('--output-root', type=Path, default=Path(__file__).resolve().parent)
a = p.parse_args()
root = a.output_root.resolve()
root.mkdir(parents=True, exist_ok=True)
source = a.repo_root.resolve()/'benchmarks/parity-import/models.kicad_pcb'
model = a.repo_root.resolve()/'benchmarks/parity-import/component-solid.step'
staged = source.read_text().replace('"models/body.step"', '"'+model.as_posix()+'"').replace('"models/lid.step"', '"'+model.as_posix()+'"')
(root/'staged.kicad_pcb').write_text(staged)
cases = []
for side in ['front','back']:
    for angle in [90,37]:
        board = pcbnew.LoadBoard(str(root/'staged.kicad_pcb'))
        fp = list(board.GetFootprints())[0]
        if side == 'back':
            fp.Flip(fp.GetPosition(), False)
        fp.SetOrientationDegrees(angle)
        name = f'{side}-{angle}'
        pcbnew.SaveBoard(str(root/(name+'.kicad_pcb')), board)
        reopened = pcbnew.LoadBoard(str(root/(name+'.kicad_pcb')))
        fp = list(reopened.GetFootprints())[0]
        cases.append({'name':name, 'side':side, 'footprint_angle_deg':fp.GetOrientationDegrees(), 'footprint_position_mm':[pcbnew.ToMM(fp.GetPosition().x),pcbnew.ToMM(fp.GetPosition().y)], 'layer':fp.GetLayerName(), 'board_thickness_mm':pcbnew.ToMM(reopened.GetDesignSettings().GetBoardThickness()), 'models':[{'model_index':i, 'source_path':m.m_Filename,'offset_mm':[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z], 'rotation_deg':[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z], 'scale':[m.m_Scale.x,m.m_Scale.y,m.m_Scale.z]} for i,m in enumerate(fp.Models())]})
        assert len(cases[-1]['models']) == 3
        assert all(m['source_path'] == model.as_posix() for m in cases[-1]['models'])
(root/'inputs.json').write_text(json.dumps({'native_version':pcbnew.GetBuildVersion(),'cases':cases},indent=2)+'\n')
print(json.dumps(cases,indent=2))
