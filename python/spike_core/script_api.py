# SPDX-License-Identifier: Apache-2.0
"""Importable API module exposed to SPIKE Python workspace scripts."""

from __future__ import annotations

import copy
import json
import sys
import types
import uuid
from typing import Any

from .automation import SpikeAutomation
from .script_api_context import MAX_UI_ACTIONS, UI_PANELS
from .script_views import ScriptViews


MAX_ACTION_ID_CHARS = 256
PANELS = UI_PANELS


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def _required_id(value: Any, label: str) -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{label} must be a string or integer ID.")
    if isinstance(value, str) and (not value or len(value) > MAX_ACTION_ID_CHARS):
        raise ValueError(f"{label} must be a nonempty ID of at most {MAX_ACTION_ID_CHARS} characters.")
    return value


class _Boards:
    def __init__(self, api: "SpikeScriptAPI") -> None:
        self._api = api

    def list(self) -> list[dict[str, Any]]:
        selected = self._api._workspace.get("selected_board_id")
        return [{"id": item["id"], "name": item["name"],
                 "design_id": item["design_id"], "selected": item["id"] == selected}
                for item in self._api._board_items]

    def get(self, board_id: str | None = None, *, name: str | None = None) -> dict[str, Any]:
        return _copy(self._api._board(board_id, name=name))


class _BoardCollection:
    def __init__(self, api: "SpikeScriptAPI", field: str, label: str,
                 id_fields: tuple[str, ...], name_fields: tuple[str, ...]) -> None:
        self._api = api
        self._field = field
        self._label = label
        self._id_fields = id_fields
        self._name_fields = name_fields

    def _items(self, board_id: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        board = self._api._board(board_id)
        value = board["design"].get(self._field, [])
        if not isinstance(value, list):
            raise ValueError(f"Board {board['id']} has an invalid {self._field} inventory.")
        return board, [item for item in value if isinstance(item, dict)]

    def list(self, board_id: str | None = None) -> list[dict[str, Any]]:
        _board, items = self._items(board_id)
        return _copy(items)

    def get(self, item_id: str | int | None = None, *, name: str | None = None,
            board_id: str | None = None) -> dict[str, Any]:
        if item_id is None and name is None:
            raise ValueError(f"A {self._label} ID or name is required.")
        _board, items = self._items(board_id)
        if item_id is not None:
            matches = [item for item in items if any(item.get(field) == item_id for field in self._id_fields)]
            detail = f"ID {item_id!r}"
        else:
            matches = [item for item in items if any(item.get(field) == name for field in self._name_fields)]
            detail = f"name {name!r}"
        if not matches:
            raise KeyError(f"Unknown {self._label} {detail}.")
        if len(matches) != 1:
            raise ValueError(f"Ambiguous {self._label} {detail}; use its canonical ID.")
        return _copy(matches[0])


class _Nets(_BoardCollection):
    def __init__(self, api: "SpikeScriptAPI") -> None:
        super().__init__(api, "nets", "net", ("id", "net_id"), ("name",))

    def get(self, net_id: str | int | None = None, *, name: str | None = None,
            board_id: str | None = None) -> dict[str, Any]:
        return super().get(net_id, name=name, board_id=board_id)


class _Layers(_BoardCollection):
    def __init__(self, api: "SpikeScriptAPI") -> None:
        super().__init__(api, "layers", "layer", ("id", "layer_id", "name"), ("name",))

    def get(self, layer_id: str | int | None = None, *, name: str | None = None,
            board_id: str | None = None) -> dict[str, Any]:
        return super().get(layer_id, name=name, board_id=board_id)


class _Components(_BoardCollection):
    def __init__(self, api: "SpikeScriptAPI") -> None:
        super().__init__(api, "components", "component",
                         ("id", "component_id", "reference", "ref"),
                         ("reference", "ref", "name"))

    def get(self, component_id: str | int | None = None, *, reference: str | None = None,
            board_id: str | None = None) -> dict[str, Any]:
        return super().get(component_id, name=reference, board_id=board_id)


class _Assembly:
    def __init__(self, api: "SpikeScriptAPI") -> None:
        self._api = api

    def connector_links(self) -> list[dict[str, Any]]:
        assembly = self._api._workspace.get("assembly", {})
        for field in ("connector_links", "connector_mappings", "connectorLinks"):
            links = assembly.get(field)
            if links is not None:
                if not isinstance(links, list) or any(not isinstance(item, dict) for item in links):
                    raise ValueError(f"workspace.assembly.{field} must be an object array.")
                return _copy(links)
        return []


class _Analysis:
    def __init__(self, api: "SpikeScriptAPI") -> None:
        self._api = api

    def catalog(self) -> dict[str, Any]:
        return {"contract": "spike/python-analysis-catalog/v1",
                "capabilities": self._api.call("capabilities"),
                "solvers": self._api.call("list_solvers")}

    def run(self, method: str, params: dict[str, Any] | None = None) -> Any:
        return self._api.call(method, params)


class _ResultData:
    def __init__(self, api: "SpikeScriptAPI") -> None:
        self._api = api

    @property
    def current(self) -> dict[str, Any] | None:
        return _copy(self._api.results)

    def get(self) -> dict[str, Any] | None:
        return self.current


class _UI:
    def __init__(self, api: "SpikeScriptAPI") -> None:
        self._api = api

    def _append(self, action: dict[str, Any]) -> dict[str, Any]:
        if len(self._api._ui_actions) >= MAX_UI_ACTIONS:
            raise ValueError(f"Python scripts may return at most {MAX_UI_ACTIONS} UI actions.")
        self._api._ui_actions.append(action)
        return _copy(action)

    def select_net(self, board_id: str, net_id: str | int) -> dict[str, Any]:
        board = self._api._board(board_id)
        requested = _required_id(net_id, "net_id")
        net = self._api.nets.get(requested, board_id=board["id"])
        canonical = next((net.get(field) for field in ("id", "net_id") if net.get(field) is not None), requested)
        return self._append({"action": "select_net", "board_id": board["id"], "net_id": canonical})

    def focus_board(self, board_id: str) -> dict[str, Any]:
        board = self._api._board(board_id)
        return self._append({"action": "focus_board", "board_id": board["id"]})

    def open_panel(self, panel: str) -> dict[str, Any]:
        if panel not in PANELS:
            raise ValueError(f"Unsupported SPIKE panel: {panel!r}.")
        return self._append({"action": "open_panel", "panel": panel})


class SpikeScriptAPI(types.ModuleType, ScriptViews):
    """Bound module facade; worker calls retain their normal admission path."""

    def __init__(self, context: dict[str, Any]) -> None:
        super().__init__("spike", "SPIKE Python workspace API")
        ScriptViews.__init__(self)
        self._workspace = context.get("workspace") or {
            "boards": [], "selected_board_id": None, "assembly": {},
        }
        self._board_items = list(self._workspace.get("boards", []))
        self.design = context.get("design")
        self.results = context.get("results")
        self._binding = context.get("design_binding")
        self._trusted_extension_ids = context.get("trusted_extension_ids", [])
        self._automation: SpikeAutomation | None = None
        self._published: dict[str, Any] | None = None
        self._ui_actions: list[dict[str, Any]] = []
        self.boards = _Boards(self)
        self.nets = _Nets(self)
        self.layers = _Layers(self)
        self.components = _Components(self)
        self.assembly = _Assembly(self)
        self.analysis = _Analysis(self)
        self.result_data = _ResultData(self)
        self.ui = _UI(self)

    def _board(self, board_id: str | None = None, *, name: str | None = None) -> dict[str, Any]:
        if board_id is None and name is None:
            board_id = self._workspace.get("selected_board_id")
            if board_id is None:
                raise ValueError("No workspace board is selected.")
        if board_id is not None:
            matches = [item for item in self._board_items if item.get("id") == board_id]
            detail = f"occurrence ID {board_id!r}"
        else:
            matches = [item for item in self._board_items if item.get("name") == name]
            detail = f"name {name!r}"
        if not matches:
            raise KeyError(f"Unknown board {detail}.")
        if len(matches) != 1:
            raise ValueError(f"Ambiguous board {detail}; use its occurrence ID.")
        return matches[0]

    def _worker(self) -> SpikeAutomation:
        if self._automation is None:
            self._automation = SpikeAutomation()
            from . import service
            for extension_id in self._trusted_extension_ids:
                service._extension_registry.trust(extension_id)
        return self._automation

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if method in {"run_python_script", "start_python_debug"}:
            raise ValueError("Nested Python workspace runs are not supported.")
        return self._worker().call(method, params)

    def extensions(self) -> Any:
        return self._worker().extension_catalog()

    def invoke_extension(self, extension_id: str, contribution_id: str,
                         parameters: dict[str, Any] | None = None) -> Any:
        catalog = self.extensions()
        entry = next((item for item in catalog.get("extensions", []) if item.get("id") == extension_id), None)
        if entry is None:
            raise ValueError(f"Extension is not installed: {extension_id}")
        permissions = entry.get("permissions", [])
        context: dict[str, Any] = {}
        if "results.read" in permissions and self.results is not None:
            context["results"] = self.results
        reply = self._worker().invoke_extension(
            extension_id, contribution_id,
            design=self.design if "design.read" in permissions else None,
            parameters=parameters, context=context)
        analysis = reply.get("data", {}).get("analysis_result") if isinstance(reply.get("data"), dict) else None
        if isinstance(analysis, dict):
            provenance = analysis.get("provenance")
            if isinstance(provenance, dict):
                analysis = {**analysis, "provenance": {
                    **provenance, "script_upstream_extension_id": extension_id}}
            self.publish_result(analysis)
        return reply

    def publish_result(self, result: dict[str, Any]) -> None:
        if self._binding is None:
            raise ValueError("Load a board before publishing an analysis result.")
        if not isinstance(result, dict):
            raise TypeError("Published result must be an AnalysisResult object.")
        try:
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Published result contains a non-finite or non-JSON value.") from exc
        self._published = result

    def publish_scalar_field(self, name: str, samples: list[dict[str, Any]], *,
                             mode: str = "dc", solver: str = "python-script",
                             model_status: str = "unvalidated",
                             summary: dict[str, Any] | None = None) -> None:
        if self._binding is None:
            raise ValueError("Load a board before publishing a field.")
        if not isinstance(name, str) or not name or not isinstance(samples, list):
            raise ValueError("Field name and sample array are required.")
        self.publish_result({
            "contract": "spike/v1", "analysis_id": f"python-{uuid.uuid4()}",
            "status": "completed", "mode": mode, "model_status": model_status,
            "summary": summary or {}, "fields": {"visualization": {
                "schema": "spike/result-visualization/v1", "scalar_fields": {name: samples}}},
            "networks": {}, "probes": [], "issues": [],
            "provenance": {"design_id": self._binding["design_id"],
                           "design_digest_sha256": self._binding["digest_sha256"],
                           "solver": solver},
        })

    @property
    def published_result(self) -> dict[str, Any] | None:
        return self._published

    @property
    def ui_actions(self) -> list[dict[str, Any]]:
        return _copy(self._ui_actions)


def bind_spike_module(context: dict[str, Any]) -> SpikeScriptAPI:
    module = SpikeScriptAPI(context)
    sys.modules["spike"] = module
    return module


__all__ = ["MAX_UI_ACTIONS", "PANELS", "SpikeScriptAPI", "bind_spike_module"]
