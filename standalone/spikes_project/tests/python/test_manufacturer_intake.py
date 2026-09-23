import importlib.util
import io
from pathlib import Path
import unittest
import zipfile

spec=importlib.util.spec_from_file_location('model_collector',Path(__file__).resolve().parents[4]/'scripts/collect_manufacturer_models.py')
collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)

class ManufacturerIntake(unittest.TestCase):
    def test_host_boundary(self):
        collector.validate_url('https://www.ti.com/lit/zip/SNOM268','ti')
        for url in ('http://www.ti.com/a','https://www.ti.com.evil.example/a','https://user@www.ti.com/a','https://localhost/a'):
            with self.assertRaises(ValueError):collector.validate_url(url,'ti')

    def test_archive_inventory_no_execution(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            archive.writestr('../sample.lib','.subckt demo a b\nR1 a b 1k\n.ends demo')
            archive.writestr('native.dll',b'not executable')
        entries=collector.inventory(data.getvalue())
        self.assertEqual(entries[0]['review']['subcircuits'][0]['pins'],['a','b'])
        self.assertEqual(entries[0]['review']['execution'],'not_approved')
        self.assertEqual(entries[1]['status'],'retained_in_archive_only')
