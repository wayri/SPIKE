import json
import math
import re
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from python.spike_core.errors import (
    ERROR_CATALOG,
    ERROR_CONTRACT,
    ErrorClassification,
    ErrorCodeFormatError,
    ErrorDomain,
    ErrorOrigin,
    SpikeError,
    UnknownErrorCodeError,
    envelope_from_exception,
    error_envelope,
    error_metadata,
    parse_error_code,
    redact_context,
)


class ErrorCodeTests(unittest.TestCase):
    def test_strict_parser_decodes_origins_and_every_classification(self):
        for origin in ErrorOrigin:
            for classification in ErrorClassification:
                text = f"SPIKE-{origin.value}-APP-{classification.value}-0042"
                parsed = parse_error_code(text)
                self.assertEqual(parsed.origin, origin)
                self.assertEqual(parsed.domain, ErrorDomain.APP)
                self.assertEqual(parsed.classification, classification)
                self.assertEqual(parsed.sequence, 42)
                self.assertEqual(str(parsed), text)

    def test_strict_parser_rejects_noncanonical_values(self):
        invalid = (
            " spike-BE-APP-E-0001",
            "SPIKE-be-APP-E-0001",
            "SPIKE-BE-UNKNOWN-E-0001",
            "SPIKE-BE-APP-X-0001",
            "SPIKE-BE-APP-E-1",
            "SPIKE-BE-APP-E-00001",
            "SPIKE-BE-APP-E-0001 ",
            "SPK-BE-APP-E-0001",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ErrorCodeFormatError):
                parse_error_code(value)
        with self.assertRaises(ErrorCodeFormatError):
            parse_error_code(123)  # type: ignore[arg-type]

    def test_error_code_constructor_rejects_untyped_enum_values(self):
        from python.spike_core.errors import ErrorCode

        with self.assertRaises(ErrorCodeFormatError):
            ErrorCode("BE", ErrorDomain.APP, ErrorClassification.ERROR, 1)  # type: ignore[arg-type]

    def test_catalog_and_metadata_are_immutable(self):
        metadata = error_metadata("SPIKE-BE-SOLVER-E-0002")
        with self.assertRaises(TypeError):
            ERROR_CATALOG["SPIKE-BE-APP-E-1234"] = metadata  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            metadata.title = "Changed"  # type: ignore[misc]

        for code, entry in ERROR_CATALOG.items():
            parsed = parse_error_code(code)
            self.assertEqual(entry.code, parsed)
            self.assertEqual(entry.docs_anchor, f"help:error-codes#{code.lower()}")

    def test_valid_but_unregistered_code_cannot_be_emitted(self):
        parsed = parse_error_code("SPIKE-BE-PI-E-9876")
        self.assertEqual(parsed.domain, ErrorDomain.PI)
        with self.assertRaises(UnknownErrorCodeError):
            error_envelope(parsed)

    def test_pdn_multiport_codes_have_canonical_metadata(self):
        expected = {
            "SPIKE-BE-PI-W-0101": (
                "PDN multiport approximation",
                ErrorClassification.WARNING,
                True,
                False,
            ),
            "SPIKE-BE-PI-E-0102": (
                "PDN candidate port extraction failed",
                ErrorClassification.ERROR,
                True,
                True,
            ),
            "SPIKE-BE-PI-P-0103": (
                "PDN candidate port limit exceeded",
                ErrorClassification.PERFORMANCE,
                True,
                True,
            ),
        }
        for code, (title, classification, recoverable, retryable) in expected.items():
            with self.subTest(code=code):
                metadata = error_metadata(code)
                self.assertEqual(metadata.title, title)
                self.assertEqual(metadata.code.classification, classification)
                self.assertEqual(metadata.recoverable, recoverable)
                self.assertEqual(metadata.retryable, retryable)


class ErrorEnvelopeTests(unittest.TestCase):
    def test_envelope_has_consistent_contract_and_code_fields(self):
        envelope = error_envelope(
            "SPIKE-BE-SPICE-E-0020",
            message="Pin VIN is not mapped.",
            detail="Assignment U1 requires an explicit pad anchor.",
            operation_id="spice.validate:17",
            cause_code="SPIKE-BE-SPICE-E-0010",
            context={"component": "U1", "pin": "VIN"},
            timestamp_utc="2026-08-11T12:30:00.250Z",
        )
        self.assertEqual(envelope["contract"], ERROR_CONTRACT)
        self.assertEqual(envelope["origin"], "BE")
        self.assertEqual(envelope["domain"], "SPICE")
        self.assertEqual(envelope["classification"], "E")
        self.assertEqual(envelope["sequence"], 20)
        self.assertEqual(envelope["operation_id"], "spice.validate:17")
        self.assertEqual(envelope["cause_code"], "SPIKE-BE-SPICE-E-0010")
        self.assertEqual(envelope["context"], {"component": "U1", "pin": "VIN"})
        json.dumps(envelope, allow_nan=False)

    def test_safe_context_redacts_secrets_and_bounds_arbitrary_values(self):
        cyclic = {}
        cyclic["self"] = cyclic
        context = redact_context(
            {
                "password": "do-not-leak",
                "nested": {"api_token": "do-not-leak", "ok": "visible"},
                "authorization_header": "Bearer abc.def.ghi",
                "endpoint": "https://user:pass@example.invalid/run",
                "binary": b"opaque",
                "not_finite": math.inf,
                "long": "x" * 2000,
                "cycle": cyclic,
                "unknown": object(),
            }
        )
        self.assertEqual(context["password"], "[REDACTED]")
        self.assertEqual(context["nested"]["api_token"], "[REDACTED]")
        self.assertEqual(context["nested"]["ok"], "visible")
        self.assertEqual(context["authorization_header"], "[REDACTED]")
        self.assertEqual(context["endpoint"], "[REDACTED]")
        self.assertEqual(context["binary"], "[REDACTED]")
        self.assertIsNone(context["not_finite"])
        self.assertLessEqual(len(context["long"]), 1024)
        self.assertEqual(context["cycle"]["self"], "[CYCLE]")
        self.assertEqual(context["unknown"], "<object>")
        json.dumps(context, allow_nan=False)

    def test_spike_error_round_trips_without_exposing_traceback(self):
        error = SpikeError(
            "SPIKE-FE-PROJECT-E-0001",
            "Project package could not be read.",
            context={"path": "C:/design/example.spike", "session_token": "private"},
        )
        self.assertIn("SPIKE-FE-PROJECT-E-0001", str(error))
        self.assertEqual(error.context["session_token"], "[REDACTED]")
        envelope = error.to_envelope(timestamp_utc="2026-08-11T12:30:00Z")
        self.assertEqual(envelope["message"], "Project package could not be read.")
        self.assertEqual(envelope["context"]["session_token"], "[REDACTED]")
        self.assertNotIn("traceback", envelope)
        self.assertNotIn("stack", envelope)

    def test_unknown_exception_uses_registered_fallback_and_redacts_message(self):
        envelope = envelope_from_exception(
            RuntimeError("Authorization: Bearer abc.def"),
            timestamp_utc="2026-08-11T12:30:00Z",
        )
        self.assertEqual(envelope["code"], "SPIKE-BE-APP-C-9999")
        self.assertEqual(envelope["context"]["exception_type"], "RuntimeError")
        self.assertEqual(envelope["context"]["exception_message"], "[REDACTED]")
        self.assertEqual(envelope["detail"], "Unhandled RuntimeError")

    def test_invalid_operation_id_and_timestamp_are_rejected(self):
        with self.assertRaises(ValueError):
            error_envelope("SPIKE-FE-APP-E-0001", operation_id="contains spaces")
        with self.assertRaises(ValueError):
            error_envelope(
                "SPIKE-FE-APP-E-0001",
                timestamp_utc="2026-99-99T00:00:00Z",
            )

    def test_schema_matches_runtime_contract_and_catalog_grammar(self):
        schema_path = Path(__file__).resolve().parents[2] / "schemas" / "error-envelope-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["contract"]["const"], ERROR_CONTRACT)
        self.assertFalse(schema["additionalProperties"])

        required = set(schema["required"])
        sample = error_envelope(
            "SPIKE-BE-MESH-P-0001",
            timestamp_utc="2026-08-11T12:30:00Z",
        )
        self.assertTrue(required.issubset(sample))
        pattern = re.compile(schema["properties"]["code"]["pattern"], flags=re.ASCII)
        for code in ERROR_CATALOG:
            self.assertIsNotNone(pattern.fullmatch(code), code)
        self.assertEqual(
            set(schema["properties"]["classification"]["enum"]),
            {item.value for item in ErrorClassification},
        )
        self.assertEqual(
            set(schema["properties"]["origin"]["enum"]),
            {item.value for item in ErrorOrigin},
        )

        catalog_path = Path(__file__).resolve().parents[2] / "docs" / "ERROR_CODE_CATALOG.md"
        catalog_text = catalog_path.read_text(encoding="utf-8")
        for code in ERROR_CATALOG:
            self.assertIn(f"`{code}`", catalog_text)


if __name__ == "__main__":
    unittest.main()
