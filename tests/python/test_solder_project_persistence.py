# SPDX-License-Identifier: Apache-2.0
"""Authored solder display data survives the real portable desktop package path."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.odb_importer import import_odb_design
from tests.python.test_odb_harness_extensions import write_board

class SolderProjectPersistenceTests(unittest.TestCase):
    def test_native_save_open_save_as_retains_solder_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            canonical=SpiDeRV2.from_v1(import_odb_design(str(write_board(directory)))).to_dict()
            canonical["source"]["artifact_path"]=""
            normalized={"contract":"spike/design-snapshot/v1","canonical_design":canonical,"design":SpiDeRV2.from_dict(canonical).to_v1().to_dict()}
            bonds=[{"id":"pin-bond","padId":"owned-pad","reference":"J1","pad":"1","net":"GND","boardInstanceId":"board-A","solderVisual":{"visible":True,"style":"through-hole","heightMm":.4,"spreadMm":.2,"opacity":.7}}]
            snapshot={"format":"spike-project-package/v2","project":{"name":"Solder model"},"design":{"source_file":"board.spike-design.json","source_format":"spike-normalized","source_board":json.dumps(normalized),"canonical_design":canonical,"component_bonds":copy.deepcopy(bonds)},"analysis":{}}
            first=Path(directory)/"first.spike"
            def request(method,**params):
                response=handle_project_request(method,params,request_id="solder-persistence",application_version="test")
                self.assertTrue(response["ok"],response)
                return response["result"]
            request("write_project_package",path=str(first),snapshot=snapshot)
            opened=request("read_project_package",path=str(first))
            self.assertEqual(opened["project"]["design"]["component_bonds"],bonds)
            before=first.read_bytes()
            second=Path(directory)/"copy.spike"
            request("write_project_package",path=str(second),snapshot=opened["project"],base_package_path=str(first))
            self.assertEqual(first.read_bytes(),before)
            self.assertEqual(request("read_project_package",path=str(second))["project"]["design"]["component_bonds"],bonds)
