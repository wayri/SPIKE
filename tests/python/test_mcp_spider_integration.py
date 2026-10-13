# SPDX-License-Identifier: Apache-2.0
import io
import json
import unittest
from unittest.mock import patch
from python.spike_core.automation import SpikeAutomation
from python.spike_core.contracts import SpiDeR
from python.spike_core.mcp_server import McpServer, TOOLS, serve
from python.spike_core.mcp_protocol import MODERN_VERSION, META_PREFIX
from python.spike_core.spider_v2 import SpiDeRV2

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.server=McpServer(SpikeAutomation())
        self.design=SpiDeR(design_id="query-fixture",name="Board",source_format="fixture",nets=[{"id":"net1","name":"VCC"}],components=[{"id":"part1","reference":"R1","at":[2,3]}]).to_dict()
    def modern(self,method,params=None):
        return self.server.handle({"jsonrpc":"2.0","id":1,"method":method,"params":{**(params or {}),"_meta":{META_PREFIX+"protocolVersion":MODERN_VERSION,META_PREFIX+"clientCapabilities":{}}}})
    def test_modern_tools_and_schema_resources_have_typed_metadata(self):
        discovered=self.modern("server/discover")["result"]
        self.assertEqual(discovered["resultType"],"complete")
        listed=self.modern("tools/list")["result"]
        tool=next(row for row in listed["tools"] if row["name"]=="spike_query_spider")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertEqual(tool["inputSchema"]["properties"]["entity_types"]["type"],"array")
        self.assertIn("outputSchema",tool)
        resources=self.modern("resources/list")["result"]
        resource=next(row for row in resources["resources"] if row["name"]=="design-ir-v2.schema.json")
        value=self.modern("resources/read",{"uri":resource["uri"]})["result"]
        self.assertEqual(json.loads(value["contents"][0]["text"])["properties"]["contract"]["const"],"spike/design-ir/v2")
    def test_actual_spider_query_normalization_and_revision_conflict(self):
        validation=self.server.call_tool("spike_validate_spider",{"document":self.design})
        self.assertFalse(validation["isError"],validation)
        report=validation["structuredContent"]
        self.assertTrue(report["ok"],report)
        self.assertEqual(report["contract"],"spider/api-result/v1")
        queried=self.server.call_tool("spike_query_spider",{"document":self.design,"entity_types":["components"],"limit":1,"expected_revision":report["document_revision"]})["structuredContent"]
        self.assertEqual(queried["entities"][0]["source_id"],"part1")
        stale=self.server.call_tool("spike_query_spider",{"document":self.design,"expected_revision":"0"*64})["structuredContent"]
        self.assertFalse(stale["ok"])
        converted=self.server.call_tool("spike_normalize_spider",{"document":self.design,"target_contract":"spike/design-ir/v2"})["structuredContent"]
        self.assertTrue(converted["ok"],converted)
        self.assertEqual(converted["normalized_document"]["contract"],"spike/design-ir/v2")
    def test_typed_filters_and_returned_schemas_cannot_mutate_registry(self):
        for filters in ({"limit":501},{"entity_types":["shell"]},{"ids":[{}]}):
            with self.assertRaises(ValueError):self.server.call_tool("spike_query_spider",{"document":self.design,**filters})
        schema=TOOLS["spike_query_spider"].schema();schema["properties"]["limit"]["maximum"]=999
        self.assertEqual(TOOLS["spike_query_spider"].schema()["properties"]["limit"]["maximum"],500)
    def test_v2_worker_projection_preserves_binding_without_mutating_caller(self):
        from python.spike_core.service import handle
        payload=SpiDeRV2.from_v1(SpiDeR(design_id="empty",name="Empty",source_format="fixture")).to_dict()
        before=json.dumps(payload,sort_keys=True)
        with patch("python.spike_core.service._dispatch",return_value={"ok":True,"result":{"status":"checked"}}) as dispatched:
            response=handle({"method":"validate_design","params":{"design":payload}})
        self.assertTrue(response["ok"],response)
        self.assertEqual(dispatched.call_args.args[0]["params"]["design"]["contract"],"spike/v1")
        self.assertIn("spider",response["meta"])
        self.assertEqual(before,json.dumps(payload,sort_keys=True))
    def test_protocol_rejects_duplicate_keys_and_does_not_dispatch_notifications(self):
        output=io.BytesIO();serve(io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"ping","method":"tools/call"}\n'),output,self.server.automation)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"],-32700)
        with patch.object(self.server,"call_tool") as call:
            self.assertIsNone(self.server.handle({"jsonrpc":"2.0","method":"tools/call","params":{"name":"spike_capabilities"}}))
        call.assert_not_called()

if __name__=="__main__":unittest.main()
