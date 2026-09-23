from copy import deepcopy
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.simulation_setup import default_thermal,default_profile,validate_thermal,validate_profile,effective_source,RunHistory


class SetupTests(unittest.TestCase):
    def test_legacy_defaults_are_independent_and_clean(self):
        doc=Document.from_netlist(RC_DECK);legacy=deepcopy(doc.data)
        legacy.pop('thermal_setup');legacy.pop('run_profile')
        restored=Document(legacy)
        self.assertFalse(restored.dirty)
        restored.data['thermal_setup']['board']['layers'][0]['copper_um']=70
        self.assertEqual(doc.data['thermal_setup']['board']['layers'][0]['copper_um'],35)

    def test_setup_save_load_undo_redo_and_source_reconciliation(self):
        doc=Document.from_netlist(RC_DECK);setup=default_thermal()
        setup['board']['length_mm']=210
        setup['environment'].update(airflow='forced',air_speed_m_s=2,ambient_c=50)
        doc.update_setup('thermal_setup',setup);self.assertTrue(doc.dirty)
        doc.undo();self.assertEqual(doc.data['thermal_setup']['board']['length_mm'],100)
        doc.redo();doc.apply_source(RC_DECK.replace('1k','2k'))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'board.spksch';doc.save(path)
            self.assertEqual(Document.load(path).data['thermal_setup'],setup)
        self.assertNotIn('.temp',doc.data['source'].lower())

    def test_invalid_thermal_transaction_is_atomic(self):
        doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
        mutations=[lambda s:s['board'].update(width_mm=0),
                   lambda s:s['environment'].update(airflow='forced',air_speed_m_s=0),
                   lambda s:s['environment'].update(ambient_c=float('nan')),
                   lambda s:s['board']['layers'].append(deepcopy(s['board']['layers'][0])),
                   lambda s:s['board'].update(thickness_mm=.01),
                   lambda s:s['enclosure'].update(type='sealed',wall_mm=30),
                   lambda s:s.update(solver_binding='coupled')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                setup=default_thermal();mutate(setup)
                with self.assertRaises(ValueError):doc.update_setup('thermal_setup',setup)
                self.assertEqual(doc.data,before)

    def test_profile_overrides_are_explicit(self):
        profile=default_profile();self.assertEqual(effective_source(RC_DECK,profile),RC_DECK)
        profile.update(analysis='transient',time_step='20u',stop_time='2m',uic=False,electrical_temperature_c=60)
        source=effective_source(RC_DECK,profile)
        self.assertIn('.tran 20u 2m\n',source);self.assertIn('.temp 60\n.end',source)
        self.assertNotIn('.temp',RC_DECK)
        profile.update(analysis='operating_point',electrical_temperature_c=None)
        self.assertIn('.op\n',effective_source(RC_DECK,profile))
        with self.assertRaises(ValueError):effective_source(RC_DECK.replace('.end','.op\n.end'),profile)
        with self.assertRaises(ValueError):effective_source(RC_DECK.replace('.tran 10u 5m uic','.tran 10u 5m\n+ uic'),profile)

    def test_invalid_profiles(self):
        for change in ({'capture_samples':1},{'capture_samples':True},{'speed_ratio':float('inf')},
                       {'execution':'continuous','analysis':'operating_point'},
                       {'time_step':'1','stop_time':'1m'},{'method':'invented'},
                       {'electrical_temperature_c':-274}):
            with self.subTest(change=change):
                profile=default_profile();profile.update(change)
                with self.assertRaises(ValueError):validate_profile(profile)

    def test_run_history_is_bounded_and_snapshots_are_independent(self):
        doc=Document.from_netlist(RC_DECK);history=RunHistory(capacity=2)
        ident=history.start(doc.data,'test.dll')
        doc.data['thermal_setup']['environment']['ambient_c']=80
        record=history.get(ident)
        self.assertEqual(record['thermal_setup']['environment']['ambient_c'],25)
        self.assertEqual(record['source_sha256'],hashlib.sha256(RC_DECK.encode()).hexdigest())
        history.update(ident,'completed',data={'time_s':[0,.001]})
        self.assertEqual(record['samples'],2);self.assertEqual(record['simulation_time_s'],.001)
        self.assertIn('ended_utc',record);self.assertNotIn('data',record)
        history.start(doc.data,'test.dll');history.start(doc.data,'test.dll')
        self.assertIsNone(history.get(ident));self.assertEqual(len(history.records),2)


if __name__=='__main__':unittest.main()
