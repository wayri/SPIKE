# SPDX-License-Identifier: Apache-2.0
"""Original geometric handoff fixture, not a PDK IC or fabrication layout.

Run inside KLayout with -b -r and -rd output_layout=NEW_FILE.gds.
"""
from pathlib import Path
import pya

target=globals().get('output_layout')
if not isinstance(target,str) or not target:raise ValueError('Specify output_layout')
if Path(target).exists():raise ValueError('Existing layout output is preserved')
layout=pya.Layout();layout.dbu=0.001
metal=layout.layer(1,0);marker=layout.layer(7,3)
unit=layout.create_cell('UNIT');unit.shapes(metal).insert(pya.Box(0,0,10000,5000))
top=layout.create_cell('TOP');top.shapes(marker).insert(pya.Box(0,0,1000,2000))
top.insert(pya.CellInstArray(unit.cell_index(),pya.Trans(pya.Trans.R90,20000,30000)))
layout.write(target)
