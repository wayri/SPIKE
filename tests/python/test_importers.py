import tempfile
import unittest
from pathlib import Path

from python.spike_core.contracts import DesignIR
from python.spike_core.importers import (
    FunctionImporter,
    ImporterDescriptor,
    ImporterRegistry,
    UnsupportedDesignFormatError,
)


class ImporterRegistryTests(unittest.TestCase):
    def importer(self, importer_id="test", extensions=(".board",)):
        return FunctionImporter(
            descriptor=ImporterDescriptor(
                importer_id=importer_id,
                display_name="Test importer",
                source_formats=(importer_id,),
                extensions=extensions,
            ),
            implementation=lambda path: DesignIR(name=Path(path).stem, source_path=path),
        )

    def test_detects_by_extension_and_records_provenance(self):
        registry = ImporterRegistry([self.importer()])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "power.board"
            source.write_text("fixture", encoding="utf-8")
            design = registry.import_design(str(source))
        self.assertEqual(design.name, "power")
        self.assertEqual(design.metadata["importer_id"], "test")
        self.assertEqual(design.metadata["importer_contract"], "spike/importer-descriptor/v1")

    def test_unknown_and_ambiguous_sources_fail_explicitly(self):
        registry = ImporterRegistry([
            self.importer("first", (".brd",)),
            self.importer("second", (".brd",)),
        ])
        with self.assertRaises(UnsupportedDesignFormatError):
            registry.detect("board.brd")
        self.assertEqual(registry.detect("board.brd", "second").descriptor.importer_id, "second")
        with self.assertRaises(UnsupportedDesignFormatError):
            registry.detect("board.unknown")

    def test_duplicate_ids_are_rejected(self):
        registry = ImporterRegistry([self.importer()])
        with self.assertRaises(ValueError):
            registry.register(self.importer())


if __name__ == "__main__":
    unittest.main()
