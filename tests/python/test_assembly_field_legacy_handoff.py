# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Exact legacy diagnostic-digest migration without physical-input weakening."""
import copy
import unittest
from python.spike_core.assembly_field_handoff import prepare_assembly_field_handoff
from python.spike_core.assembly_field_thermal import run_assembly_field_thermal, verify_assembly_field_result, _legacy_handoff_digest
from python.spike_core.assembly_field_study import import_assembly_field_study
from python.spike_core.multiboard_identity import canonical_json_digest
from tests.python.test_assembly_field_handoff import fixture


def digest(record, field):
    record[field]=canonical_json_digest({k:v for k,v in record.items() if k!=field})


def legacy_fixture():
    request,problem=fixture()
    handoff=prepare_assembly_field_handoff(request)
    legacy=copy.deepcopy(handoff)
    points=legacy['mesh']['vertices']
    bounds=[(min(points[i][0] for i in c['vertices']),max(points[i][0] for i in c['vertices'])) for c in legacy['mesh']['cells']]
    # Independent literal original pair-sweep counter, including same-owner cells.
    order=sorted(range(len(bounds)),key=lambda i:bounds[i][0])
    count=0
    for offset,a in enumerate(order):
        for b in order[offset+1:]:
            if bounds[b][0]>=bounds[a][1]: break
            count+=1
    legacy['geometry_audit']['inter_occurrence_comparisons']=count
    digest(legacy,'handoff_digest')
    result=run_assembly_field_thermal(request,problem)
    result['handoff_digest']=legacy['handoff_digest']
    result['field_result']['heat_balance'].pop('radiation_outward_w')
    result['field_result']['diagnostics'].pop('newton_iterations')
    digest(result,'result_digest')
    record={'contract':'spike/assembly-field-study-file/v1','request':request,'problem':problem,'result':result}
    digest(record,'file_digest')
    return record,handoff,legacy


class LegacyHandoffTests(unittest.TestCase):
    def test_exact_legacy_result_migrates_copy_preserving_all_field_values(self):
        record,current,legacy=legacy_fixture()
        before=copy.deepcopy(record)
        self.assertNotEqual(current['handoff_digest'],legacy['handoff_digest'])
        self.assertEqual(_legacy_handoff_digest(current),legacy['handoff_digest'])
        migrated=import_assembly_field_study(record)
        self.assertEqual(record,before)
        self.assertEqual(migrated['result']['handoff_digest'],current['handoff_digest'])
        self.assertEqual(migrated['result']['field_result'],record['result']['field_result'])
        self.assertEqual(migrated['result']['source_traceability'],record['result']['source_traceability'])
        self.assertNotEqual(migrated['file_digest'],record['file_digest'])
        self.assertEqual(import_assembly_field_study(migrated),migrated)

    def test_arbitrary_counter_and_metadata_digests_are_not_accepted(self):
        for edit in [lambda h:h['geometry_audit'].update(inter_occurrence_comparisons=31),
                     lambda h:h['limitations'].append('altered metadata')]:
            record,_,legacy=legacy_fixture()
            edit(legacy);digest(legacy,'handoff_digest')
            record['result']['handoff_digest']=legacy['handoff_digest']
            digest(record['result'],'result_digest');digest(record,'file_digest')
            with self.assertRaisesRegex(ValueError,'STALE'):
                import_assembly_field_study(record)

    def test_original_integrity_problem_and_physical_bindings_remain_mandatory(self):
        record,_,_=legacy_fixture()
        broken=copy.deepcopy(record);broken['result']['field_result']['node_temperatures_k'][0]+=1
        digest(broken,'file_digest')
        with self.assertRaisesRegex(ValueError,'RESULT_DIGEST'):
            import_assembly_field_study(broken)
        broken=copy.deepcopy(record);broken['result']['handoff_digest']='x'
        with self.assertRaisesRegex(ValueError,'STUDY_DIGEST'):
            import_assembly_field_study(broken)
        for mutate in [lambda r,p:r['materials'][0].update(thermal_conductivity_w_mk=3),
                       lambda r,p:p['boundaries'][0].update(temperature_k=310)]:
            broken=copy.deepcopy(record);mutate(broken['request'],broken['problem'])
            with self.assertRaisesRegex(ValueError,'STALE'):
                verify_assembly_field_result(broken['request'],broken['problem'],broken['result'])

    def test_unavailable_legacy_budget_has_explicit_recovery(self):
        # 709 mutually overlapping x intervals imply 250986 old comparisons.
        current={'mesh':{'vertices':[[0,0,0],[1,0,0],[0,1,0],[0,0,1]],
                         'cells':[{'vertices':[0,1,2,3]} for _ in range(709)]}}
        with self.assertRaisesRegex(ValueError,'legacy handoff exceeded.*rerun'):
            _legacy_handoff_digest(current)
