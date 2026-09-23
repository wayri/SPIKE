from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.command_registry import CommandRegistry,Command,Context
from spikes_studio.workbench_layout import preset,validate,PRESETS


class WorkbenchFoundations(unittest.TestCase):
    def test_dispatch_and_context_are_shared(self):
        state=Context(selected=0);called=[]
        registry=CommandRegistry.from_actions({'edit.rotate':lambda:called.append('rotate')},lambda:state)
        with self.assertRaisesRegex(ValueError,'Select'):registry.execute('edit.rotate')
        self.assertEqual(called,[])
        state=Context(selected=2)
        registry.execute('edit.rotate');self.assertEqual(called,['rotate'])
        state=Context(page='Plots',schematic=False,selected=2)
        with self.assertRaisesRegex(ValueError,'schematic'):registry.execute('edit.rotate')
        with self.assertRaises(ValueError):registry.register(Command('edit.rotate','duplicate',lambda:None))

    def test_search_keys_and_unavailable_reason(self):
        registry=CommandRegistry.from_actions({'run.pause':lambda:None,'view.fit':lambda:None},lambda:Context())
        rows=registry.search('pause',{'run.pause':'F6'})
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['shortcut'],'F6')
        self.assertIn('continuous',rows[0]['disabled_reason'])
        self.assertEqual(registry.search('no_such_command'),[])

    def test_profiles_validate_before_applying(self):
        for name in PRESETS:self.assertEqual(validate(preset(name)),preset(name))
        original=preset('Power electronics')
        for changes in ({'split':1},{'page':'missing'},{'contract':'new-version'},{'script':'exec()'}):
            with self.assertRaises(ValueError):validate(original|changes,['Schematic'])
