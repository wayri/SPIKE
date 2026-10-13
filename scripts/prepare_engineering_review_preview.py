# SPDX-License-Identifier: Apache-2.0
"""Generate cached original backend results for the isolated UI verification page."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.python.test_engineering_review import request
from python.spike_core.engineering_review import review_engineering,quick_engineering_tool

review=request();review['overrides']=[]
quick={'contract':'spike/quick-engineering-tool-request/v1','tool':'resistor_divider',
       'vin':'5','r_top_ohm':'10000','r_bottom_ohm':'10000'}
output=ROOT/'app/.tmp/engineering-review.json'
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps({'request':review,'result':review_engineering(review),
    'quick_request':quick,'quick_result':quick_engineering_tool(quick)},indent=2),encoding='utf-8')
print(output)
