# SPDX-License-Identifier: Apache-2.0
"""Read-only sheet definition import and geometric fold preview worker routes."""
from .service_helpers import error_response


def handle_sheet_folding_request(method, params):
    if method not in {"import_sheet_definition", "preview_sheet_fold"}:
        return None
    try:
        if not isinstance(params, dict):
            raise ValueError("Sheet operation parameters must be an object.")
        from .sheet_folding import import_sheet_text, fold_sheet
        if method == "import_sheet_definition":
            if set(params) != {"contents", "source_format"}:
                raise ValueError("Sheet import requires contents and source_format only.")
            contents = params["contents"]
            if not isinstance(contents, str) or len(contents.encode("utf-8")) > 4_000_000:
                raise ValueError("Sheet import requires UTF-8 text no larger than 4 MB.")
            result = {"sheet": import_sheet_text(contents, params["source_format"])}
        else:
            if set(params) != {"sheet", "fraction"}:
                raise ValueError("Fold preview requires sheet and fraction only.")
            result = {"preview": fold_sheet(params["sheet"], fraction=params["fraction"])}
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", str(exc), context={"method": method})
