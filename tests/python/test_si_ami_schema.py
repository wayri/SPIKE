# SPDX-License-Identifier: Apache-2.0
"""Offline structural checks; semantic admission remains in the AMI decoder."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from python.spike_core import si_ami_inventory as ami
from tests.python.test_si_ami_inventory import package


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "si-ami-package-request-v1.schema.json"


class AmiPackageSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_schema_identity_fixture_and_decoder_agree_without_external_refs(self):
        self.assertEqual(self.schema["$id"], ami.PACKAGE_REQUEST_CONTRACT)
        request = package()
        self.validator.validate(request)
        self.assertFalse(ami.inspect_ami_package(request)["execution_admitted"])

        def check_references(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "$ref":
                        self.assertTrue(value.startswith("#/"))
                    check_references(value)
            elif isinstance(node, list):
                for value in node:
                    check_references(value)
        check_references(self.schema)

    def test_missing_and_unknown_fields_rejected_at_every_object(self):
        for path in (None, "parameter_file", "executable_file"):
            baseline = package()
            target = baseline if path is None else baseline[path]
            for key in list(target) + ["unknown"]:
                request = deepcopy(baseline)
                modified = request if path is None else request[path]
                if key == "unknown":
                    modified[key] = True
                else:
                    modified.pop(key)
                with self.subTest(path=path, key=key):
                    self.assertFalse(self.validator.is_valid(request))

    def test_exact_string_bounds_match_decoder_constants(self):
        props = self.schema["properties"]
        text_schema = props["parameter_file"]["properties"]["text"]
        binary_schema = props["executable_file"]["properties"]["base64"]
        self.assertEqual(text_schema["maxLength"], ami.MAX_TEXT_BYTES)
        self.assertEqual(binary_schema["maxLength"], 4 * ((ami.MAX_BINARY_BYTES + 2) // 3))
        for definition, maximum, fill in ((text_schema, ami.MAX_TEXT_BYTES, "x"),
                                          (binary_schema, binary_schema["maxLength"], "A"),
                                          (self.schema["$defs"]["member_name"], 256, "a")):
            validator = Draft202012Validator(definition)
            with self.subTest(maximum=maximum):
                self.assertTrue(validator.is_valid(fill * maximum))
                self.assertFalse(validator.is_valid(fill * (maximum + 1)))
                self.assertFalse(validator.is_valid(""))

    def test_platform_direction_ascii_digest_and_scalar_types(self):
        for platform in ("Linux_gcc-14.2_64", "Windows_MSVC_32", "O" * 119 + "_cc_64"):
            request = package()
            request["platform"] = platform
            self.validator.validate(request)
        for value in ("Windows_MSVC_128", "Windows_extra_MSVC_64", "_MSVC_64", "Windows__64",
                      "Windows_MSVC_64\n", "Windows MSVC_64", "O" * 123 + "_cc_64", None, True):
            request = package()
            request["platform"] = value
            with self.subTest(platform=value):
                self.assertFalse(self.validator.is_valid(request))
        mutations = (
            (None, "direction", "both"), (None, "contract", "wrong"),
            ("parameter_file", "path", "wrong.AMI"), ("parameter_file", "path", "x.ami\n"),
            ("parameter_file", "text", "x\x00"), ("parameter_file", "text", "\u00e9"),
            ("parameter_file", "text", 12), ("parameter_file", "sha256", "F" * 64),
            ("executable_file", "sha256", "0" * 63), ("executable_file", "base64", "AA==\n"),
            ("executable_file", "base64", "!!!!"), ("executable_file", "base64", ["AA=="]),
        )
        for path, key, value in mutations:
            request = package()
            (request if path is None else request[path])[key] = value
            with self.subTest(path=path, key=key, value=value):
                self.assertFalse(self.validator.is_valid(request))

    def test_schema_does_not_replace_semantic_decoder_admission(self):
        for path, key, value in (("parameter_file", "sha256", "0" * 64),
                                 ("parameter_file", "path", "../escape.ami"),
                                 ("executable_file", "base64", "AB==")):
            request = package()
            request[path][key] = value
            with self.subTest(path=path, key=key):
                self.validator.validate(request)
                with self.assertRaises(ami.SiAmiInventoryError):
                    ami.inspect_ami_package(request)


if __name__ == "__main__":
    unittest.main()
