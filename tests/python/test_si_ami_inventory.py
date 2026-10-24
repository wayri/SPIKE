# SPDX-License-Identifier: Apache-2.0
"""Original synthetic AMI inventory fixtures; no external model or code."""
from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from python.spike_core import si_ami_inventory as ami


def document(model: str = "", *, impulse: str = "True", wave: str = "False", version: str = "8.0") -> str:
    return f'''(CopperFox
      (Reserved_Parameters
        (AMI_Version (Usage Info) (Type String) (Value "{version}"))
        (Init_Returns_Impulse (Type Boolean) (Default {impulse}) (Usage Info))
        (GetWave_Exists (Usage Info) (Type Boolean) (Value {wave})))
      {model}
      (Description "Original synthetic inventory fixture"))'''


def parameter(body: str, name: str = "Gain") -> str:
    return document(f"(Model_Specific ({name} {body}))")


def package() -> dict:
    text = document()
    binary = b"SPIKE inert invented bytes, not a native library\x00\xff"
    return {"contract": ami.PACKAGE_REQUEST_CONTRACT, "direction": "rx", "platform": "Windows_MSVC_64",
            "parameter_file": {"path": "params/copper.ami", "text": text, "sha256": sha256(text.encode()).hexdigest()},
            "executable_file": {"path": "model/copper.dll", "base64": base64.b64encode(binary).decode(),
                                "sha256": sha256(binary).hexdigest()}}


class AmiParameterInventoryTests(unittest.TestCase):
    def test_recursive_typed_inventory_and_exact_source_identity(self):
        text = document('''(Model_Specific (Equalizer
          (Description "Group detail")
          (Gain (Usage In) (Type Float) (Format Range 1.25 -2 4) (Default 2))
          (Delay (Usage InOut) (Type UI) (Corner 0.125 0.2 -0.1))
          (Tap (Usage In) (Type Tap) (Value -0.375))
          (Count (Usage In) (Type Integer) (Value 13e2))))''')
        result = ami.parse_ami_parameters(text, "authored.ami")
        self.assertEqual(result["sha256"], sha256(text.encode()).hexdigest())
        self.assertEqual(result["size_bytes"], len(text))
        self.assertEqual(result["root_name"], "CopperFox")
        self.assertEqual(result["parameters"][3]["path"], ["Model_Specific", "Equalizer", "Gain"])
        self.assertEqual(result["parameters"][3]["values"], [1.25, -2.0, 4.0])
        self.assertEqual(result["parameters"][3]["default"], 2.0)
        self.assertEqual(result["parameters"][4]["default"], 0.125)
        self.assertEqual(result["parameters"][6]["values"], [1300])
        self.assertIn({"path": ["Model_Specific", "Equalizer"], "description": "Group detail"}, result["groups"])
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertFalse(result["execution_admitted"])
        self.assertFalse(result["abi_verified"])

    def test_comments_strings_case_sensitive_names_and_duplicate_list_values(self):
        text = document('''| A source comment with unmatched delimiters ) ((
          (Model_Specific
            (Case (Usage In) (Type String) (List "x | ()" "y" "y")
             (List_Tip "choice x" "choice y" "choice y") (Default "y"))
            (case (Usage Out) (Type String) (Value "line one
line two\\literal")))''')
        result = ami.parse_ami_parameters(text)
        self.assertEqual(result["parameters"][3]["values"], ["x | ()", "y", "y"])
        self.assertIsNone(result["parameters"][4]["default"])
        self.assertEqual(result["parameters"][4]["values"], ["line one\nline two\\literal"])

    def test_duplicate_branches_and_descriptors_fail_closed(self):
        for body in (
            "(Usage In) (Usage Info) (Type Float) (Value 1)",
            "(Usage In) (Type Float) (Value 1) (Format Value 1)",
            "(Usage In) (Type Float) (Value 1) (Default 1)",
        ):
            with self.subTest(body=body), self.assertRaises(ami.SiAmiInventoryError):
                ami.parse_ami_parameters(parameter(body))
        for text in (document("(Model_Specific (A) (A))"), document("(Reserved_Parameters)")):
            with self.assertRaisesRegex(ami.SiAmiInventoryError, "duplicate"):
                ami.parse_ami_parameters(text)

    def test_invalid_scalar_types_ranges_defaults_and_formats_are_rejected(self):
        for kind, form in (
            ("Float", "Value nan"), ("Float", "Value 1e999"), ("Float", "Value 1e-999"),
            ("Float", "Value 2p"), ("Float", 'Value "1"'), ("Boolean", "Value true"),
            ("Boolean", "Value 1"), ("String", "Value unquoted"),
            ("Integer", "Value 1.0"), ("Integer", "Value 10e-1"),
            ("Integer", "Value 2147483648"), ("Integer", "Value -2147483649"),
            ("Float", "Range 9 0 8"), ("String", 'Range "a" "b" "c"'),
            ("Float", "Corner 1 2"), ("Float", "Gaussian 0 1"),
            ("Float", "Steps 0 0 1 4"), ("Float", "Increment 0 0 1 0.1"),
            ("Float", "Table (1 2)"), ("Unknown", "Value 0"),
        ):
            with self.subTest(kind=kind, form=form), self.assertRaises(ami.SiAmiInventoryError):
                ami.parse_ami_parameters(parameter(f"(Usage In) (Type {kind}) ({form})"))
        for body in (
            "(Usage In) (Type Float) (List 1 2) (Default 3)",
            "(Usage In) (Type Float) (Range 1 0 2) (Default -1)",
            "(Usage Out) (Type Float) (Default 0)",
            "(Usage Out) (Type Float) (Corner 0 1 2)",
            '(Usage In) (Type Float) (List 1 2) (List_Tip "same" "same")',
            '(Usage In) (Type Float) (List 1 1) (List_Tip "a" "b")',
            '(Usage In) (Type Float) (List 1) (List_Tip "")',
            '(Usage In) (Type Float) (Value 1) (List_Tip "a")',
        ):
            with self.subTest(body=body), self.assertRaises(ami.SiAmiInventoryError):
                ami.parse_ami_parameters(parameter(body))

    def test_integer_limits_boolean_values_and_default_alias(self):
        for token, expected in (("-2147483648", -2147483648), ("2147483647", 2147483647), ("13e+2", 1300)):
            parsed = ami.parse_ami_parameters(parameter(f"(Usage In) (Type Integer) (Default {token})"))
            self.assertEqual(parsed["parameters"][-1]["default"], expected)
        parsed = ami.parse_ami_parameters(parameter("(Usage In) (Type Boolean) (List True False) (Default False)"))
        self.assertIs(parsed["parameters"][-1]["default"], False)

    def test_reserved_checks_and_unknown_semantics_remain_explicit(self):
        for text in (document(impulse="False", wave="False"), document(version="9.0"), document(version="5.0"),
                     document().replace("(AMI_Version", "(Version"),
                     document().replace("(Type Boolean)", "(Type Integer)"),
                     document().replace("(Usage Info)", "(Usage In)", 1)):
            with self.subTest(text=text), self.assertRaises(ami.SiAmiInventoryError):
                ami.parse_ami_parameters(text)
        extra = "(VendorReserved (Usage Info) (Type Float) (Value 0.75))"
        text = document().replace("(GetWave_Exists", extra + " (GetWave_Exists")
        result = ami.parse_ami_parameters(text)
        self.assertEqual(result["unvalidated_reserved_parameters"], [["Reserved_Parameters", "VendorReserved"]])
        self.assertEqual(result["status"], "inventory_only")
        self.assertFalse(result["execution_admitted"])
        with self.assertRaisesRegex(ami.SiAmiInventoryError, "first"):
            ami.parse_ami_parameters(text.replace("(AMI_Version", extra + " (AMI_Version", 1).replace(extra + " (GetWave_Exists", "(GetWave_Exists"))
        with self.assertRaisesRegex(ami.SiAmiInventoryError, "6.1"):
            ami.parse_ami_parameters(parameter("(Usage Dep) (Type Float) (Value 1)").replace('"8.0"', '"6.0"'))

    def test_malformed_tokens_roots_encoding_and_unknown_branches(self):
        for text in ("", "()", "(a", "(a))", "(a)(b)", "bare", document() + " junk",
                     document().replace("CopperFox", '"unterminated'),
                     document().replace("CopperFox", "bad\x00name"),
                     document().replace("CopperFox", "nonascii\u00e9"),
                     document("(Model_Specific ((Gain)))"), document("(Other)"),
                     document().replace('"8.0"', '"8.0"bad')):
            with self.subTest(text=text[:80]), self.assertRaises(ami.SiAmiInventoryError):
                ami.parse_ami_parameters(text)

    def test_all_resource_bounds_are_checked_before_unbounded_work(self):
        for constant, bound, text in (("MAX_TEXT_BYTES", 10, document()), ("MAX_TOKENS", 10, document()),
                                      ("MAX_TOKEN_CHARS", 3, document()), ("MAX_NODES", 3, document()),
                                      ("MAX_PARAMETERS", 2, document()), ("MAX_DEPTH", 3, document())):
            with self.subTest(constant=constant), patch.object(ami, constant, bound), self.assertRaises(ami.SiAmiInventoryError):
                ami.parse_ami_parameters(text)
        with self.assertRaisesRegex(ami.SiAmiInventoryError, "depth"):
            ami.parse_ami_parameters("(a " * 1000 + ")" * 1000)
        with patch.object(ami, "MAX_RESULT_BYTES", 32), self.assertRaisesRegex(ami.SiAmiInventoryError, "response budget"):
            ami.parse_ami_parameters(document())

    def test_group_order_and_optional_resolve_declaration(self):
        text = document().replace("(GetWave_Exists", "(Resolve_Exists (Usage Info) (Type Boolean) (Value True)) (GetWave_Exists")
        result = ami.parse_ami_parameters(text)
        self.assertEqual(result["unvalidated_reserved_parameters"], [])
        self.assertEqual(result["parameters"][2]["path"], ["Reserved_Parameters", "Resolve_Exists"])
        wrong_order = document().replace("(Reserved_Parameters", "(Model_Specific) (Reserved_Parameters", 1)
        with self.assertRaisesRegex(ami.SiAmiInventoryError, "precede"):
            ami.parse_ami_parameters(wrong_order)

    def test_nested_dependent_parameters_require_a_true_resolver(self):
        text = document('(Model_Specific (Receiver (Adaptation (Usage Dep) (Type Float) (Value 0.25))))')
        for resolver in (None, "False"):
            source = text if resolver is None else text.replace(
                "(GetWave_Exists", f"(Resolve_Exists (Usage Info) (Type Boolean) (Value {resolver})) (GetWave_Exists")
            with self.subTest(resolver=resolver), self.assertRaisesRegex(ami.SiAmiInventoryError, "Resolve_Exists"):
                ami.parse_ami_parameters(source)
        source = text.replace("(GetWave_Exists", "(Resolve_Exists (Usage Info) (Type Boolean) (Value True)) (GetWave_Exists")
        result = ami.parse_ami_parameters(source)
        self.assertEqual(result["parameters"][-1]["path"], ["Model_Specific", "Receiver", "Adaptation"])
        self.assertEqual(result["parameters"][-1]["usage"], "Dep")
        self.assertFalse(result["execution_admitted"])
        with self.assertRaisesRegex(ami.SiAmiInventoryError, "6.1"):
            ami.parse_ami_parameters(source.replace('"8.0"', '"6.0"'))

    def test_descriptor_fragments_are_not_groups_and_sections_are_containers(self):
        for descriptor in ("Default", "Range", "List_Tip", "Format", "List", "Corner", "Value", "Usage", "Type"):
            with self.subTest(descriptor=descriptor), self.assertRaises(ami.SiAmiInventoryError):
                ami.parse_ami_parameters(document(f"(Model_Specific (Gain ({descriptor})))"))
        for section in ("Model_Specific", "Reserved_Parameters"):
            source = document("(Model_Specific (Usage In) (Type Float) (Value 1))") if section == "Model_Specific" else document().replace(
                "(Reserved_Parameters", "(Reserved_Parameters (Usage In) (Type Float) (Value 1)", 1)
            with self.subTest(section=section), self.assertRaisesRegex(ami.SiAmiInventoryError, "container"):
                ami.parse_ami_parameters(source)
        result = ami.parse_ami_parameters(document('''(Model_Specific
            (Description "Section detail") (Receiver (Description "Group detail")
                (Gain (Usage In) (Type Float) (Range 0.5 0 1))))'''))
        self.assertEqual(result["parameters"][-1]["path"], ["Model_Specific", "Receiver", "Gain"])
        self.assertEqual(result["groups"][-1]["description"], "Group detail")

    def test_resource_bounded_mutations_raise_only_inventory_errors(self):
        # Deterministic punctuation/control mutations of our own fixture, not
        # a vendor corpus or a general conformance proof.
        source = document()
        for index in range(0, len(source), 7):
            for replacement in ('(', ')', '"', '|', '\x00'):
                mutated = source[:index] + replacement + source[index + 1:]
                try:
                    result = ami.parse_ami_parameters(mutated)
                except ami.SiAmiInventoryError:
                    continue
                self.assertFalse(result["execution_admitted"])
                json.dumps(result, allow_nan=False)


class AmiPackageInventoryTests(unittest.TestCase):
    def test_bytes_are_hashed_but_never_loaded_or_opened(self):
        request = package()
        original = deepcopy(request)
        with patch("builtins.open", side_effect=AssertionError("no filesystem")), \
                patch("ctypes.CDLL", side_effect=AssertionError("no loading")), \
                patch("subprocess.Popen", side_effect=AssertionError("no processes")):
            result = ami.inspect_ami_package(request)
        self.assertEqual(request, original)
        self.assertEqual(result["declared_platform"], {"os": "Windows", "compiler": "MSVC", "bits": 64})
        self.assertEqual(result["declared_direction"], "rx")
        self.assertEqual(result["members"][1]["sha256"], request["executable_file"]["sha256"])
        self.assertFalse(result["execution_admitted"])
        self.assertFalse(result["abi_verified"])
        self.assertNotIn("base64", json.dumps(result))

    def test_paths_digests_base64_and_exact_keys_fail_closed(self):
        for target, field, value in (
            ("parameter_file", "path", "../escape.ami"), ("parameter_file", "path", "/absolute.ami"),
            ("parameter_file", "path", "C:/absolute.ami"), ("parameter_file", "path", "a\\b.ami"),
            ("parameter_file", "path", "CON.ami"), ("parameter_file", "path", "x/./a.ami"),
            ("parameter_file", "path", "x /a.ami"), ("parameter_file", "path", "x//a.ami"),
            ("parameter_file", "path", "wrong.txt"), ("parameter_file", "sha256", "0" * 64),
            ("executable_file", "sha256", "0" * 64), ("executable_file", "base64", "!!!!"),
            ("executable_file", "base64", "AA==\n"), ("executable_file", "base64", "AB=="),
            ("executable_file", "base64", ""), ("executable_file", "path", "params/copper.ami"),
        ):
            request = package()
            request[target][field] = value
            with self.subTest(target=target, field=field, value=value), self.assertRaises(ami.SiAmiInventoryError):
                ami.inspect_ami_package(request)
        for field, value in (("platform", "Windows_MSVC_128"), ("platform", "too_many_fields_64"),
                             ("direction", "bidirectional"), ("contract", "wrong"), ("extra", True)):
            request = package()
            request[field] = value
            with self.subTest(field=field), self.assertRaises(ami.SiAmiInventoryError):
                ami.inspect_ami_package(request)
        for target in ("parameter_file", "executable_file"):
            request = package()
            request[target]["extra"] = True
            with self.assertRaises(ami.SiAmiInventoryError):
                ami.inspect_ami_package(request)

    def test_binary_limit_is_enforced_before_decode(self):
        with patch.object(ami, "MAX_BINARY_BYTES", 3), patch.object(ami.base64, "b64decode") as decode:
            with self.assertRaisesRegex(ami.SiAmiInventoryError, "bounded"):
                ami.inspect_ami_package(package())
            decode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
