# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from python.spike_core.assembly_em import prepare_assembly_em
from python.spike_core.assembly_em_study import admit_assembly_em_study
from tests.python.test_assembly_em import fixture


def study():
    request=fixture()
    prepared=prepare_assembly_em(request)
    dataset={'positions_m':[[0,0,.002]],'vectors':[[[1,0],[0,2],[0,0]]],
             'native_indices':[0],'source_sample_count':1,'sample_stride':1}
    return {'contract':'spike/assembly-em-study/v1','request':request,'result':{
        'contract':'spike/assembly-em-result/v1','status':'completed','solver_executed':True,
        'production_qualified':False,'model_status':'unvalidated',
        'request_digest':prepared['request_digest'],'assembly_digest':prepared['assembly_digest'],
        'compiled_digest':prepared['compiled']['compiled_digest'],
        'frequency_hz':request['settings']['frequency_hz'],'excited_port_id':'drive',
        's_parameter_column':[{'port_id':'drive','real':[.5]*3,'imag':[.1]*3}],
        'field_capture':{'preview':{'contract':'spike/assembly-em-preview/v1','normalization':'1V_peak_incident',
            'coordinate_frame':'assembly','coordinate_units':'m','frequency_hz':request['settings']['frequency_hz'][-1],
            'datasets':{'electric-field':{**copy.deepcopy(dataset),'units':'V/m'},
                        'magnetic-field':{**copy.deepcopy(dataset),'units':'A/m'}}}}}}


class AssemblyEmStudyTests(unittest.TestCase):
    def test_result_free_package_keeps_request(self):
        from python.spike_core.service_project_persistence import without_saved_results
        value={'analyses':{'retained_assembly_em':{'request':{'ports':[1]},'result':{'sample':2}}}}
        clean=without_saved_results(value)
        self.assertIsNone(clean['analyses']['retained_assembly_em']['result'])
        self.assertEqual(clean['analyses']['retained_assembly_em']['request'],{'ports':[1]})
        self.assertEqual(value['analyses']['retained_assembly_em']['result'],{'sample':2})

    def test_complete_and_setup_only_records_admit(self):
        value=study()
        self.assertEqual(admit_assembly_em_study(value),value)
        value['result']=None
        self.assertIsNone(admit_assembly_em_study(value)['result'])

    def test_stale_geometry_and_status_rejected(self):
        for key,value in [('request_digest','a'*64),('compiled_digest','b'*64),
                          ('assembly_digest','c'*64),('production_qualified',True),('model_status','validated')]:
            record=study();record['result'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):admit_assembly_em_study(record)

    def test_malformed_field_and_port_samples_rejected(self):
        record=study();record['result']['s_parameter_column'][0]['real'][1]=float('nan')
        with self.assertRaises(ValueError):admit_assembly_em_study(record)
        for change in ('units','positions','vectors','indices'):
            record=study();data=record['result']['field_capture']['preview']['datasets']['electric-field']
            if change=='units':data['units']='arbitrary'
            elif change=='positions':data['positions_m'][0][1]=float('inf')
            elif change=='vectors':data['vectors'][0][2]=[1]
            else:data['native_indices']=[1]
            with self.subTest(change=change),self.assertRaises(ValueError):admit_assembly_em_study(record)

    def test_normalization_and_frame_are_not_inferred(self):
        for key,value in [('normalization','raw_gaussian_pulse_dft'),('coordinate_frame','board'),('coordinate_units','mm')]:
            record=study();record['result']['field_capture']['preview'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):admit_assembly_em_study(record)
