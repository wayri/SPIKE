"""Canonical error identifiers/envelopes; only registered codes may be emitted."""
from __future__ import annotations
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from .error_catalog_pi import PI_ERROR_SPECS
ERROR_CONTRACT = "spike/error/v1"
class ErrorOrigin(str, Enum):
    """The process tier that first detected an event."""
    FRONTEND = "FE"
    BACKEND = "BE"
class ErrorClassification(str, Enum):
    """Operational classification encoded in every SPIKE error code."""
    INFORMATION = "I"
    WARNING = "W"
    PERFORMANCE = "P"
    ERROR = "E"
    CRITICAL = "C"
    SECURITY = "S"


class ErrorDomain(str, Enum):
    """Stable ownership domains used by the canonical catalog."""

    APP = "APP"
    PROJECT = "PROJECT"
    PACKAGE = "PACKAGE"
    IMPORT = "IMPORT"
    VIEW = "VIEW"
    PI = "PI"
    SI = "SI"
    THERMAL = "THERMAL"
    EMI = "EMI"
    SPICE = "SPICE"
    SOLVER = "SOLVER"
    MESH = "MESH"
    PROBE = "PROBE"
    REPORT = "REPORT"
    EXT = "EXT"
    IPC = "IPC"
    SECURITY = "SECURITY"


_DOMAIN_ALTERNATION = "|".join(domain.value for domain in ErrorDomain)
ERROR_CODE_PATTERN = (
    rf"^SPIKE-(FE|BE)-({_DOMAIN_ALTERNATION})-(I|W|P|E|C|S)-([0-9]{{4}})$"
)
_ERROR_CODE_RE = re.compile(ERROR_CODE_PATTERN, flags=re.ASCII)


class ErrorCodeFormatError(ValueError):
    """Raised when a value is not a canonical SPIKE error code."""


class UnknownErrorCodeError(ValueError):
    """Raised when a valid code has no immutable catalog entry."""


@dataclass(frozen=True, slots=True)
class ErrorCode:
    origin: ErrorOrigin
    domain: ErrorDomain
    classification: ErrorClassification
    sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.origin, ErrorOrigin):
            raise ErrorCodeFormatError("Error-code origin must be an ErrorOrigin")
        if not isinstance(self.domain, ErrorDomain):
            raise ErrorCodeFormatError("Error-code domain must be an ErrorDomain")
        if not isinstance(self.classification, ErrorClassification):
            raise ErrorCodeFormatError(
                "Error-code classification must be an ErrorClassification"
            )
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ErrorCodeFormatError("Error-code sequence must be an integer")
        if not 0 <= self.sequence <= 9999:
            raise ErrorCodeFormatError("Error-code sequence must be between 0000 and 9999")

    def __str__(self) -> str:
        return (
            f"SPIKE-{self.origin.value}-{self.domain.value}-"
            f"{self.classification.value}-{self.sequence:04d}"
        )


def parse_error_code(value: str | ErrorCode) -> ErrorCode:
    """Parse *value* without normalization or case folding.

    Leading/trailing whitespace, unknown domains, aliases, and non-four-digit
    sequences are rejected. Passing an ``ErrorCode`` returns it unchanged.
    """

    if isinstance(value, ErrorCode):
        return value
    if not isinstance(value, str):
        raise ErrorCodeFormatError("Error code must be a string")
    match = _ERROR_CODE_RE.fullmatch(value)
    if match is None:
        raise ErrorCodeFormatError(
            "Expected SPIKE-{FE|BE}-{DOMAIN}-{I|W|P|E|C|S}-{NNNN}"
        )
    origin, domain, classification, sequence = match.groups()
    return ErrorCode(
        origin=ErrorOrigin(origin),
        domain=ErrorDomain(domain),
        classification=ErrorClassification(classification),
        sequence=int(sequence),
    )


@dataclass(frozen=True, slots=True)
class ErrorMetadata:
    """Immutable, user-facing metadata for one issued code."""

    code: ErrorCode
    title: str
    default_message: str
    recoverable: bool
    retryable: bool
    user_action: str
    docs_anchor: str


def _metadata(
    code: str,
    title: str,
    default_message: str,
    *,
    recoverable: bool,
    retryable: bool,
    user_action: str,
) -> ErrorMetadata:
    parsed = parse_error_code(code)
    return ErrorMetadata(
        code=parsed,
        title=title,
        default_message=default_message,
        recoverable=recoverable,
        retryable=retryable,
        user_action=user_action,
        docs_anchor=f"help:error-codes#{code.lower()}",
    )


_CATALOG_ENTRIES = (
    _metadata(
        "SPIKE-FE-APP-I-0001",
        "Operation status",
        "The requested frontend operation reported a status update.",
        recoverable=True,
        retryable=False,
        user_action="No action is required.",
    ),
    _metadata(
        "SPIKE-FE-APP-W-0001",
        "Frontend operation warning",
        "The frontend completed an operation with a condition that requires review.",
        recoverable=True, retryable=True,
        user_action="Review the associated object and suggested recovery before continuing.",
    ),
    _metadata(
        "SPIKE-FE-APP-E-0001",
        "Frontend operation failed",
        "The requested frontend operation could not be completed.",
        recoverable=True,
        retryable=True,
        user_action="Review the operation details, correct the input, and retry.",
    ),
    _metadata(
        "SPIKE-FE-APP-C-9999",
        "Unexpected frontend failure",
        "The application encountered an unexpected frontend failure.",
        recoverable=False,
        retryable=False,
        user_action="Preserve the diagnostic record and restart SPIKE.",
    ),
    _metadata(
        "SPIKE-FE-IPC-E-0001",
        "Worker unavailable",
        "The frontend could not communicate with the local analysis worker.",
        recoverable=True,
        retryable=True,
        user_action="Restart the worker or the application, then retry the operation.",
    ),
    _metadata(
        "SPIKE-FE-IPC-E-0002",
        "Malformed worker response",
        "The worker returned a response that does not satisfy its contract.",
        recoverable=False,
        retryable=False,
        user_action="Preserve the diagnostic record and verify component versions.",
    ),
    _metadata(
        "SPIKE-FE-VIEW-P-0001",
        "Viewport performance degraded",
        "The viewport exceeded its configured frame-time budget.",
        recoverable=True,
        retryable=True,
        user_action="Reduce visible detail or select a lower rendering quality preset.",
    ),
    _metadata(
        "SPIKE-FE-PROJECT-E-0001",
        "Project open failed",
        "The selected project could not be opened by the frontend.",
        recoverable=True,
        retryable=True,
        user_action="Check the project path and package integrity, then retry.",
    ),
    _metadata(
        "SPIKE-FE-SPICE-E-0001",
        "SPICE assistant input invalid",
        "The SPICE model assistant contains invalid or incomplete input.",
        recoverable=True,
        retryable=True,
        user_action="Correct the highlighted model, pin, or analysis fields and validate again.",
    ),
    _metadata(
        "SPIKE-BE-APP-C-9999",
        "Unexpected backend failure",
        "The backend encountered an unexpected failure.",
        recoverable=False,
        retryable=False,
        user_action="Preserve the diagnostic record and restart the affected worker.",
    ),
    _metadata(
        "SPIKE-BE-IPC-E-0001",
        "Invalid worker request",
        "The backend received a request that does not satisfy the worker contract.",
        recoverable=True,
        retryable=True,
        user_action="Correct the request payload and retry.",
    ),
    _metadata(
        "SPIKE-BE-IPC-E-0002",
        "Unknown worker method",
        "The requested worker method is not supported by this backend version.",
        recoverable=False,
        retryable=False,
        user_action="Verify frontend and backend versions and use a supported method.",
    ),
    _metadata(
        "SPIKE-BE-IMPORT-W-0001",
        "Import quality warning",
        "The design imported with incomplete or ambiguous source data.",
        recoverable=True,
        retryable=False,
        user_action="Review the import-quality report before configuring an analysis.",
    ),
    _metadata(
        "SPIKE-BE-IMPORT-E-0001",
        "Design import failed",
        "The source design could not be converted into the canonical import contract.",
        recoverable=True,
        retryable=True,
        user_action="Review the source path, format hint, and importer diagnostics, then retry.",
    ),
    _metadata(
        "SPIKE-BE-IMPORT-E-0002",
        "MCAD assembly import failed",
        "The STEP or glTF artifact could not be safely attached to the SPIKE project.",
        recoverable=True,
        retryable=True,
        user_action="Save the project, verify the MCAD file and embedded resources, then retry the import.",
    ),
    _metadata(
        "SPIKE-BE-MESH-W-0001",
        "Mesh validity warning",
        "The generated mesh contains a condition that may limit result validity.",
        recoverable=True,
        retryable=True,
        user_action="Inspect the mesh diagnostics and refine the affected geometry or settings.",
    ),
    _metadata(
        "SPIKE-BE-MESH-W-0002",
        "Copper polygon is unusable",
        "An imported copper polygon is invalid, self-intersecting, empty, or cannot be triangulated.",
        recoverable=True,
        retryable=True,
        user_action="Repair or refill the identified copper zone in the source design, re-import it, and inspect the mesh preview.",
    ),
    _metadata(
        "SPIKE-BE-MESH-W-0003",
        "Pad geometry approximated",
        "A pad shape is represented by extracted bounding dimensions instead of its exact polygon.",
        recoverable=True,
        retryable=False,
        user_action="Inspect the identified pad in the mesh preview and use a polygon-preserving import path when exact geometry is required.",
    ),
    _metadata(
        "SPIKE-BE-MESH-W-0004",
        "Copper geometry skipped",
        "A copper primitive has invalid or unusable dimensions and was excluded from the mesh.",
        recoverable=True,
        retryable=True,
        user_action="Inspect the identified copper object, repair its dimensions in the source design, and re-import before solving.",
    ),
    _metadata(
        "SPIKE-BE-MESH-E-0001",
        "Conductor mesh escaped source geometry",
        "A field-solver conductor volume is outside its canonical track, zone, pad, or via owner.",
        recoverable=True,
        retryable=True,
        user_action="Inspect the identified source geometry and mesh settings; do not solve until ownership validation passes.",
    ),
    _metadata(
        "SPIKE-BE-MESH-E-0002",
        "Pad drill consumes copper land",
        "A drilled pad has no positive annular copper region because its drill is as large as or larger than the pad land.",
        recoverable=True,
        retryable=True,
        user_action="Correct the pad or drill dimensions in the source design and re-import before meshing.",
    ),
    _metadata("SPIKE-BE-MESH-E-0003", "Via transition geometry is unsupported", "A via type, span, land, plating, or explicit antipad cannot enter the exact circular transition contract.",
              recoverable=True, retryable=True, user_action="Provide supported circular source geometry and explicit reference-plane antipads, then rebuild the transition."),
    _metadata("SPIKE-BE-MESH-E-0004", "Via transition discrete topology is invalid", "A circular transition mesh failed provenance, resource, orientation, manifold, or reference-void validation.", recoverable=True, retryable=True, user_action="Inspect the source-bound transition and use a supported bounded radial tessellation before solver handoff."),
    _metadata("SPIKE-BE-MESH-E-0005", "Native via transition handoff was rejected", "A source-bound via transition failed the strict native geometry admission boundary.", recoverable=True, retryable=True, user_action="Rebuild and validate the transition geometry and mesh before native handoff."),
    _metadata("SPIKE-BE-MESH-E-0006", "Via transition mesh quality gate failed", "A native-admitted transition failed exact geometry quality or bounded domain-convergence policy.", recoverable=True, retryable=True, user_action="Inspect the per-level geometry errors and conditioning warnings, then refine or repair the source transition."),
    _metadata("SPIKE-BE-MESH-E-0007", "Reference plane antipad geometry is unsupported", "A complete source reference zone or explicit antipad failed the bounded exact geometry contract.", recoverable=True, retryable=True, user_action="Repair the source zone or antipad ownership and use an admitted bounded topology before meshing."),
    _metadata("SPIKE-BE-MESH-E-0008", "Reference plane antipad mesh is invalid", "A complete source-zone mesh failed constrained-boundary, antipad-void, resource, or closed-topology validation.", recoverable=True, retryable=True, user_action="Inspect the source-bound plane and rebuild it with an admitted deterministic tessellation policy."),
    _metadata("SPIKE-BE-MESH-E-0009", "Native reference plane antipad handoff was rejected", "A complete source-bound reference-plane antipad mesh failed the strict native geometry admission boundary.", recoverable=True, retryable=True, user_action="Rebuild and validate the complete reference-plane geometry and mesh before native handoff."),
    _metadata("SPIKE-BE-MESH-E-0010", "Reference plane antipad mesh quality gate failed", "A native-admitted complete reference-plane mesh failed exact discrete-geometry quality or bounded domain-convergence policy.", recoverable=True, retryable=True, user_action="Inspect per-level geometry discrepancies, clearance, and conditioning, then refine or repair the source plane."),
    _metadata("SPIKE-BE-MESH-E-0011", "General reference plane topology is invalid", "A concave source plane, source cutout, or explicit antipad failed exact-grid topology, separation, identity, or resource admission.", recoverable=True, retryable=True, user_action="Repair touching, crossing, nested, off-grid, or unsupported curved source boundaries before meshing."),
    _metadata("SPIKE-BE-MESH-E-0012", "Bounded curve plane topology is invalid", "A DesignIR line or circular-arc boundary failed deterministic flattening, grid, curve-envelope separation, topology, identity, or resource admission.", recoverable=True, retryable=True, user_action="Repair the source curve or increase physical separation; fixed production geometry limits are not silently relaxed."),
    _metadata("SPIKE-BE-MESH-E-0013", "General reference plane mesh is invalid", "A generalized exact-grid plane mesh failed constraint, cutout, antipad, extrusion, cancellation, resource, or closed-topology admission.", recoverable=True, retryable=True, user_action="Repair the source constraints or use an admitted bounded tessellation and resource policy before native handoff."),
    _metadata("SPIKE-BE-MESH-E-0014", "Native generalized plane handoff was rejected", "A generalized source-bound plane mesh failed native digest, loop, surface-role, ownership, resource, or closed-orientation admission.", recoverable=True, retryable=True, user_action="Regenerate the generalized mesh and repair incomplete loops or provenance before native handoff."),
    _metadata("SPIKE-BE-MESH-E-0015", "Generalized plane mesh quality gate failed", "A generalized native-admitted plane failed deterministic antipad geometry convergence, conditioning, cancellation, or resource policy.", recoverable=True, retryable=True, user_action="Inspect the refinement series and repair source constraints or conditioning before field qualification."),
    _metadata("SPIKE-BE-MESH-E-0016", "Custom pad resolved geometry is unsupported", "A custom pad lacks an admitted resolved boundary/drill combination or failed contained mesh generation.", recoverable=True, retryable=True, user_action="Use an admitted filled boundary with no drill or one centered contained plated circle/oval drill."),
    _metadata("SPIKE-BE-MESH-E-0017", "Board mesh ownership accounting failed", "A supplied conductor volume escaped its canonical owner, source accounting was incomplete, or the ownership resource/cancellation contract was not satisfied.", recoverable=True, retryable=True, user_action="Inspect the source, net scope, omitted/unsupported records, and resource limits; do not hand the mesh to a solver until the ownership sidecar passes."),
    _metadata("SPIKE-BE-MESH-E-0018", "Zone-pad connection evidence failed", "Retained pad, footprint, or zone policy could not be resolved against digest-bound source-filled copper evidence.", recoverable=True, retryable=True, user_action="Repair the retained connection policy or source-filled geometry; do not infer or regenerate thermal spokes."),
    _metadata("SPIKE-BE-MESH-E-0019", "Thermal boundary-contact evidence failed", "A retained thermal-policy candidate could not be observed on a bounded polygonal pad boundary or failed digest, provenance, cancellation, or resource admission.", recoverable=True, retryable=True, user_action="Repair source-filled component provenance or pad geometry; do not label boundary intervals as thermal spokes."),
    _metadata("SPIKE-BE-MESH-E-0020", "Observed thermal topology failed", "A controlled source-filled attachment profile failed component, width, gap, reservoir, angle, digest, cancellation, or resource admission.", recoverable=True, retryable=True, user_action="Repair the controlled fixture geometry or retained thermal parameters; do not treat observed topology as refill provenance."),
    _metadata("SPIKE-BE-MESH-P-0001", "Mesh resource budget exceeded", "The requested mesh exceeds the configured time or memory budget.",
        recoverable=True,
        retryable=True,
        user_action="Increase the approved budget or use a coarser validated mesh policy.",
    ),
    _metadata(
        "SPIKE-BE-SOLVER-I-0001",
        "Solver progress",
        "The solver reported a progress update.",
        recoverable=True,
        retryable=False,
        user_action="No action is required.",
    ),
    _metadata(
        "SPIKE-BE-SOLVER-E-0001",
        "Solver unavailable",
        "No installed solver satisfies the requested capability and validity policy.",
        recoverable=True,
        retryable=False,
        user_action="Select or install an eligible solver and validate the setup again.",
    ),
    _metadata(
        "SPIKE-BE-SOLVER-E-0002",
        "Solver failed to converge",
        "The solver did not converge within its declared numerical limits.",
        recoverable=True,
        retryable=True,
        user_action="Review conditioning and mesh diagnostics before changing solver limits.",
    ),
    _metadata(
        "SPIKE-BE-SOLVER-E-0003",
        "Solver execution cancelled",
        "The active solver or co-simulation was cancelled before it completed.",
        recoverable=True,
        retryable=True,
        user_action="Review any partial diagnostics, then run the analysis again when ready.",
    ),
    _metadata(
        "SPIKE-BE-SOLVER-P-0004",
        "Solver time budget exceeded",
        "The active solver or co-simulation exceeded its configured wall-time budget.",
        recoverable=True,
        retryable=True,
        user_action="Increase the approved time budget or reduce the validated model complexity.",
    ),
    _metadata(
        "SPIKE-BE-SOLVER-W-0005",
        "Linear residual is elevated",
        "The solved linear system has a scaled residual above the preferred engineering threshold.",
        recoverable=True,
        retryable=True,
        user_action="Review disconnected geometry, resistance ratios, terminal placement, and mesh convergence before using the result.",
    ),
    _metadata(
        "SPIKE-BE-SOLVER-P-0005",
        "Interactive result data decimated",
        "Interactive geometry or result records were reduced to remain within the configured display budget.",
        recoverable=True,
        retryable=True,
        user_action="Increase the approved result-detail budget for full export, or keep decimation enabled for responsive inspection.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-E-0001",
        "SPICE workspace contract invalid",
        "The SPICE workspace does not satisfy the supported contract.",
        recoverable=True,
        retryable=True,
        user_action="Correct the workspace contract and validate it again.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-S-0001",
        "Unsafe SPICE content blocked",
        "The SPICE workspace contains content prohibited by the execution policy.",
        recoverable=False,
        retryable=False,
        user_action="Remove the prohibited directive or import a reviewed immutable model.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-E-0010",
        "SPICE model invalid",
        "A SPICE model definition is incomplete or invalid.",
        recoverable=True,
        retryable=True,
        user_action="Correct the model definition and validate the workspace again.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-E-0020",
        "SPICE assignment invalid",
        "A component or pin assignment is incomplete or inconsistent.",
        recoverable=True,
        retryable=True,
        user_action="Map every required model pin to an explicit design anchor.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-E-0030",
        "SPICE parasitic mapping invalid",
        "A parasitic element has invalid terminals, units, or provenance.",
        recoverable=True,
        retryable=True,
        user_action="Review terminal mapping, units, and extraction provenance.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-W-0031",
        "SPICE parasitic model unvalidated",
        "A parasitic model is outside its validated use or frequency range.",
        recoverable=True,
        retryable=False,
        user_action="Use a validated extraction or explicitly limit the requested analysis.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-P-0040",
        "SPICE transient budget exceeded",
        "The transient setup exceeds its configured point, time, or memory budget.",
        recoverable=True,
        retryable=True,
        user_action="Adjust duration, step size, outputs, or the approved resource budget.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-E-0041",
        "Field/circuit coupling request invalid",
        "The closed-loop field/circuit request, circuit stage, or convergence controls are invalid.",
        recoverable=True,
        retryable=True,
        user_action="Review the circuit workspace, coupling controls, and explicit terminal mappings.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-E-0042",
        "Field reduction response invalid",
        "The field adapter returned an invalid result or attempted to change reviewed coupling topology.",
        recoverable=True,
        retryable=True,
        user_action="Inspect the field adapter diagnostics and preserve the reviewed parasitic IDs and endpoints.",
    ),
    _metadata(
        "SPIKE-BE-SPICE-E-0043",
        "PEEC field mapping invalid",
        "The native PEEC result could not be mapped to the reviewed circuit parasitics.",
        recoverable=True,
        retryable=True,
        user_action="Re-extract the PEEC network and review its explicit circuit endpoint mapping before rerunning co-simulation.",
    ),
    _metadata("SPIKE-BE-SPICE-E-0054", "Owned SPICE bridge execution failed", "The structured workspace passed admission but the release-owned circuit engine bridge failed.", recoverable=True, retryable=True, user_action="Inspect the owned-engine status, workspace validation, and bounded execution diagnostics."),
    _metadata(
        "SPIKE-BE-EXT-E-0001",
        "External engine launch failed",
        "A configured external engine could not be started or completed.",
        recoverable=True,
        retryable=True,
        user_action="Review engine discovery and process diagnostics before retrying.",
    ),
    _metadata(
        "SPIKE-BE-EXT-S-0001",
        "External engine trust failure",
        "The external engine or adapter failed integrity or trust verification.",
        recoverable=False,
        retryable=False,
        user_action="Do not execute the engine; restore a trusted signed installation.",
    ),
    _metadata(
        "SPIKE-BE-PACKAGE-E-0001",
        "Project package invalid",
        "The project package is corrupt, incomplete, or incompatible.",
        recoverable=True,
        retryable=False,
        user_action="Open a verified backup or re-import the source design.",
    ),
    _metadata(
        "SPIKE-BE-PACKAGE-E-0002",
        "Project package write failed",
        "The project could not be written as a verified SPIKE package.",
        recoverable=True,
        retryable=True,
        user_action="Choose a writable destination, verify available space, and retry.",
    ),
    _metadata(
        "SPIKE-BE-REPORT-E-0001",
        "Report generation failed",
        "The engineering report could not be generated.",
        recoverable=True,
        retryable=True,
        user_action="Review the report diagnostics and retry with a writable destination.",
    ),
) + tuple(
    _metadata(
        code,
        title,
        message,
        recoverable=recoverable,
        retryable=retryable,
        user_action=user_action,
    )
    for code, title, message, recoverable, retryable, user_action in PI_ERROR_SPECS
)


ERROR_CATALOG: Mapping[str, ErrorMetadata] = MappingProxyType(
    {str(entry.code): entry for entry in _CATALOG_ENTRIES}
)

if len(ERROR_CATALOG) != len(_CATALOG_ENTRIES):  # pragma: no cover - import-time invariant
    raise RuntimeError("Duplicate canonical error codes in ERROR_CATALOG")
def error_metadata(code: str | ErrorCode) -> ErrorMetadata:
    """Return immutable catalog metadata or reject an unregistered code."""

    key = str(parse_error_code(code))
    try:
        return ERROR_CATALOG[key]
    except KeyError as exc:
        raise UnknownErrorCodeError(f"Unregistered SPIKE error code: {key}") from exc


_SENSITIVE_KEY_RE = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|authorization|cookie|credential|"
    r"private[_-]?key|license[_-]?key|session)",
    flags=re.IGNORECASE | re.ASCII,
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?:\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+|"
    r"[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@)",
    flags=re.IGNORECASE | re.ASCII,
)
_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", flags=re.ASCII)
_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$",
    flags=re.ASCII,
)
_REDACTED = "[REDACTED]"
_TRUNCATED = "[TRUNCATED]"
_MAX_CONTEXT_DEPTH = 6
_MAX_CONTEXT_ITEMS = 64
_MAX_CONTEXT_TEXT = 1024


def _safe_text(value: str, limit: int) -> str:
    if _SENSITIVE_VALUE_RE.search(value):
        return _REDACTED
    if len(value) <= limit:
        return value
    suffix = "...[TRUNCATED]"
    return value[: limit - len(suffix)] + suffix


def _safe_context_value(value: Any, depth: int, active: set[int]) -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _safe_text(value, _MAX_CONTEXT_TEXT)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _REDACTED
    if depth >= _MAX_CONTEXT_DEPTH:
        return _TRUNCATED

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            return "[CYCLE]"
        active.add(identity)
        try:
            result: dict[str, Any] = {}
            items = list(value.items())
            visible_limit = _MAX_CONTEXT_ITEMS - (1 if len(items) > _MAX_CONTEXT_ITEMS else 0)
            for key, nested in items[:visible_limit]:
                safe_key = _safe_text(str(key), 128)
                if _SENSITIVE_KEY_RE.search(str(key)):
                    result[safe_key] = _REDACTED
                else:
                    result[safe_key] = _safe_context_value(nested, depth + 1, active)
            if len(items) > visible_limit:
                result["_truncated_items"] = len(items) - visible_limit
            return result
        finally:
            active.remove(identity)

    if isinstance(value, (list, tuple, set, frozenset)):
        identity = id(value)
        if identity in active:
            return "[CYCLE]"
        active.add(identity)
        try:
            members = list(value)
            if isinstance(value, (set, frozenset)):
                members.sort(key=lambda item: (type(item).__name__, str(item)))
            safe = [
                _safe_context_value(item, depth + 1, active)
                for item in members[:_MAX_CONTEXT_ITEMS]
            ]
            if len(members) > _MAX_CONTEXT_ITEMS:
                safe.append(_TRUNCATED)
            return safe
        finally:
            active.remove(identity)

    if isinstance(value, BaseException):
        return {
            "type": type(value).__name__,
            "message": _safe_text(str(value), _MAX_CONTEXT_TEXT),
        }
    return f"<{type(value).__name__}>"


def redact_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a bounded JSON-safe copy with credentials and secrets removed."""

    if context is None:
        return {}
    if not isinstance(context, Mapping):
        raise TypeError("Error context must be a mapping")
    redacted = _safe_context_value(context, 0, set())
    if not isinstance(redacted, dict):  # pragma: no cover - guarded by type check
        raise TypeError("Error context must produce an object")
    return redacted


def _timestamp_utc(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        raise ValueError("timestamp_utc must be an RFC 3339 UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp_utc is not a valid calendar timestamp") from exc
    return value


def error_envelope(
    code: str | ErrorCode,
    *,
    message: str | None = None,
    detail: str | None = None,
    context: Mapping[str, Any] | None = None,
    operation_id: str | None = None,
    cause_code: str | ErrorCode | None = None,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    """Create a contract-compliant envelope for a registered error code."""

    metadata = error_metadata(code)
    resolved_message = metadata.default_message if message is None else message
    if not isinstance(resolved_message, str) or not resolved_message.strip():
        raise ValueError("Error message must be a non-empty string")
    parsed = metadata.code
    envelope: dict[str, Any] = {
        "contract": ERROR_CONTRACT,
        "code": str(parsed),
        "origin": parsed.origin.value,
        "domain": parsed.domain.value,
        "classification": parsed.classification.value,
        "sequence": parsed.sequence,
        "title": metadata.title,
        "message": _safe_text(resolved_message.strip(), 512),
        "recoverable": metadata.recoverable,
        "retryable": metadata.retryable,
        "user_action": metadata.user_action,
        "docs_anchor": metadata.docs_anchor,
        "timestamp_utc": _timestamp_utc(timestamp_utc),
        "context": redact_context(context),
    }
    if detail is not None:
        if not isinstance(detail, str):
            raise TypeError("Error detail must be a string")
        envelope["detail"] = _safe_text(detail, 4096)
    if operation_id is not None:
        if not isinstance(operation_id, str) or _OPERATION_ID_RE.fullmatch(operation_id) is None:
            raise ValueError("operation_id contains unsupported characters or is too long")
        envelope["operation_id"] = operation_id
    if cause_code is not None:
        envelope["cause_code"] = str(error_metadata(cause_code).code)
    return envelope


class SpikeError(RuntimeError):
    """Exception carrying a registered code and safe envelope inputs."""

    def __init__(
        self,
        code: str | ErrorCode,
        message: str | None = None,
        *,
        detail: str | None = None,
        context: Mapping[str, Any] | None = None,
        cause_code: str | ErrorCode | None = None,
    ) -> None:
        metadata = error_metadata(code)
        resolved_message = metadata.default_message if message is None else message
        if not isinstance(resolved_message, str) or not resolved_message.strip():
            raise ValueError("Error message must be a non-empty string")
        self.error_code = metadata.code
        self.code = str(metadata.code)
        self.message = _safe_text(resolved_message.strip(), 512)
        if detail is not None and not isinstance(detail, str):
            raise TypeError("Error detail must be a string")
        self.detail = _safe_text(detail, 4096) if detail is not None else None
        self.context = redact_context(context)
        self.cause_code = str(error_metadata(cause_code).code) if cause_code is not None else None
        super().__init__(f"[{self.code}] {self.message}")

    def to_envelope(
        self,
        *,
        operation_id: str | None = None,
        timestamp_utc: str | None = None,
    ) -> dict[str, Any]:
        return error_envelope(
            self.error_code,
            message=self.message,
            detail=self.detail,
            context=self.context,
            operation_id=operation_id,
            cause_code=self.cause_code,
            timestamp_utc=timestamp_utc,
        )


def envelope_from_exception(
    error: BaseException,
    *,
    fallback_code: str | ErrorCode = "SPIKE-BE-APP-C-9999",
    operation_id: str | None = None,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    """Convert an exception without exposing a traceback or arbitrary repr."""

    if isinstance(error, SpikeError):
        return error.to_envelope(operation_id=operation_id, timestamp_utc=timestamp_utc)
    return error_envelope(
        fallback_code,
        detail=f"Unhandled {type(error).__name__}",
        context={"exception_type": type(error).__name__, "exception_message": str(error)},
        operation_id=operation_id,
        timestamp_utc=timestamp_utc,
    )
__all__ = [
    "ERROR_CATALOG",
    "ERROR_CODE_PATTERN",
    "ERROR_CONTRACT",
    "ErrorClassification",
    "ErrorCode",
    "ErrorCodeFormatError",
    "ErrorDomain",
    "ErrorMetadata",
    "ErrorOrigin",
    "SpikeError",
    "UnknownErrorCodeError",
    "envelope_from_exception",
    "error_envelope",
    "error_metadata",
    "parse_error_code",
    "redact_context",
]
