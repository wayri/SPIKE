# SPDX-License-Identifier: Apache-2.0
"""Typed additive MCP descriptors; execution remains in the SPIKE worker."""
from .spider_api_validation import ENTITY_TYPES

_OBJECT = {"type":"object"}
_PAGE = {"offset":{"type":"integer","minimum":0},"limit":{"type":"integer","minimum":1,"maximum":500}}
_TYPES = {"type":"array","minItems":1,"uniqueItems":True,"items":{"type":"string","enum":list(ENTITY_TYPES)}}
_FILTER = {"type":"array","maxItems":256,"uniqueItems":True,"items":{"type":"string","minLength":1,"maxLength":256}}
_REVISION = {"type":"string","pattern":"^[a-f0-9]{64}$"}
_ISSUES = {"type":"integer","minimum":1,"maximum":500}
_RESULT = {"type":"object","required":["contract","method","ok"],"properties":{"contract":{"const":"spider/api-result/v1"},"method":{"type":"string"},"ok":{"type":"boolean"}},"additionalProperties":True}

def descriptors():
    query = {**_PAGE,"entity_types":_TYPES,"ids":_FILTER,"source_ids":_FILTER,"name_contains":{"type":"string","maxLength":256},"expected_revision":_REVISION}
    return {
      "spike_spider_capabilities":{"method":"spider_capabilities","description":"Discover SpiDeR contracts, units, reference and revision checks, projection limits and bounded query/diff operations.","read_only":True,"output_schema":_RESULT},
      "spike_validate_spider":{"method":"validate_spider","description":"Validate inline SpiDeR v1/v2 structure, units, finite geometry and entity references; validation is not solver qualification.","required":("document",),"optional":("max_issues",),"integer_keys":("max_issues",),"property_schemas":{"max_issues":_ISSUES},"read_only":True,"output_schema":_RESULT},
      "spike_normalize_spider":{"method":"normalize_spider","description":"Normalize inline SpiDeR into a supported contract, retaining revision and explicit projection loss reports. Does not modify any project.","required":("document",),"optional":("target_contract","max_issues"),"string_keys":("target_contract",),"integer_keys":("max_issues",),"enums":(("target_contract",("spike/v1","spike/design-ir/v2")),),"property_schemas":{"max_issues":_ISSUES},"read_only":True,"output_schema":_RESULT},
      "spike_query_spider":{"method":"query_spider","description":"Read bounded canonical entities and outgoing reference identities from inline SpiDeR. Supply expected_revision to reject stale pagination.","required":("document",),"optional":tuple(query),"integer_keys":("offset","limit"),"string_keys":("name_contains","expected_revision"),"array_keys":("entity_types","ids","source_ids"),"property_schemas":query,"read_only":True,"output_schema":_RESULT},
      "spike_compare_spider":{"method":"compare_spider","description":"Compare inline design revisions deterministically; page added, removed and changed entities and inspect source/frame drift. No changes are applied.","required":("before","after"),"optional":("entity_types","offset","limit"),"array_keys":("entity_types",),"integer_keys":("offset","limit"),"property_schemas":{**_PAGE,"entity_types":_TYPES},"read_only":True,"output_schema":_RESULT},
      "spike_validate_spice_workspace":{"method":"validate_spice_workspace","description":"Validate explicit circuit models, board part and physical pin assignments against SpiDeR; no compact models are inferred.","required":("design","workspace"),"optional":("assembly_scope",),"read_only":True},
      "spike_compose_spice_workspace":{"method":"compose_spice_workspace","description":"Compose a reviewed circuit workspace into a deterministic netlist with node and component aliases. No solver or file write.","required":("design","workspace"),"optional":("assembly_scope",),"read_only":True},
      "spike_studio_board_context":{"method":"prepare_studio_board_context","description":"Read current board component aliases and the exact revision required by Studio feedback requests.","required":("design",),"read_only":True},
      "spike_validate_studio_feedback":{"method":"validate_studio_board_cosimulation","description":"Admit supplied board-bound electrical/thermal/conductor feedback. Missing values and unsupported devices remain rejected.","required":("design","request"),"optional":("assembly_scope",),"read_only":True},
      "spike_run_studio_feedback":{"method":"run_studio_board_cosimulation","description":"Run approximate board-bound steady/transient RLC and supported ideal-source feedback with explicit thermal and conductor parameters. No spatial FEM or inferred semiconductor losses.","required":("design","request"),"optional":("assembly_scope",)},
      "spike_gui_studio_board_context":{"method":"gui:studio_board_context","description":"Read exact loaded-board component aliases and revision required for an admitted Studio feedback case; caller cannot substitute a board.","read_only":True},
      "spike_gui_spider_context":{"method":"gui:spider_context","description":"Inspect the loaded board's SpiDeR revision and validation summary without exporting the full board.","read_only":True},
      "spike_gui_spider_query":{"method":"gui:spider_query","description":"Query canonical part, copper, layer, net and reference records in the loaded board, with bounded pages and optional revision binding.","optional":("query",),"property_schemas":{"query":{"type":"object","properties":query,"additionalProperties":False}},"read_only":True},
      "spike_gui_spider_compare":{"method":"gui:spider_compare","description":"Compare a supplied prior SpiDeR document to the loaded board; return paged changes, never apply edits.","required":("before",),"optional":("query",),"property_schemas":{"query":{"type":"object","properties":{**_PAGE,"entity_types":_TYPES},"additionalProperties":False}},"read_only":True},
    }
