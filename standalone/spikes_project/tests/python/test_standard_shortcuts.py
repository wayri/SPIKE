import unittest
from spikes_studio.document import Keymap


class StandardShortcuts(unittest.TestCase):
    def test_defaults_and_profiles_are_conflict_free(self):
        keys=Keymap().bindings
        for command,key in {'edit.copy':'Ctrl+C','edit.select_all':'Ctrl+A',
                            'edit.paste':'Ctrl+V','edit.undo':'Ctrl+Z','edit.redo':'Ctrl+Y',
                            'edit.properties_standard':'Ctrl+E','edit.rotate_standard':'Ctrl+R',
                            'file.export':'Ctrl+Shift+E'}.items():
            self.assertEqual(keys[command],key)
        for profile in ('SPIKES','KiCad-inspired','LTspice-inspired'):
            Keymap.preset(profile).validate()
        self.assertEqual(Keymap.preset('LTspice-inspired').bindings['run.start'],'Ctrl+R')

    def test_custom_profile_remains_explicit(self):
        profile={'contract':'spikes/shortcuts/v2','bindings':{'edit.copy':'Alt+C'},'part_shortcuts':False}
        self.assertEqual(Keymap.from_data(profile).to_data(),profile)
