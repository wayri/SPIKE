"""Round-trip a real board and captured import stages through desktop persistence."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.spike_core.service_project_handlers import handle_project_request


def request(method, **params):
    response = handle_project_request(method, params, request_id="portable-project-qa", application_version="0.2.10")
    if not response["ok"]:
        raise RuntimeError(response)
    return response["result"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("captures", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    artifacts = []
    responses = {}
    for stage in ("layout", "board", "components"):
        response = json.loads((args.captures / f"{stage}-response.json").read_text(encoding="utf-8-sig"))["result"]
        responses[stage] = response
        for role, artifact in response["scenes"].items():
            artifacts.append({**artifact, "role": role})
        for layer, artifact in response["layout"]["layers"].items():
            artifacts.append({**artifact, "role": f"layer:{layer}"})
    visuals = {"contract": "spike/saved-board-visuals/v1", "artifacts": artifacts,
               "view_box": responses["layout"]["layout"]["view_box"],
               "quality": responses["components"]["quality"],
               "board_includes_copper": responses["board"]["quality"].get("board_includes_copper", True)}
    runs = [{"analysis_id": f"run-{i}", "outputs": {"time_s": [0, 1], "voltage_v": [i, i + 1]},
             "future_output": {"units": "V"}} for i in range(25)]
    snapshot = {"format": "spike-project-package/v2", "project": {"name": args.board.stem},
                "design": {"source_file": args.board.name, "source_format": "kicad_pcb", "source_board": args.board.read_text(encoding="utf-8")},
                "analysis": {"latest_result": runs[-1], "result_history": [{"id": item["analysis_id"], "bundle": item} for item in runs]}}
    saved = request("write_project_package", path=str(args.output), snapshot=snapshot, visuals=visuals)
    opened = request("read_project_package", path=str(args.output), defer_artifacts=True)
    for stage, original in responses.items():
        restored = request("read_project_visual_bundle", path=str(args.output), stage=stage,
                           index=opened["project"]["board_visuals"], expected_manifest_payload_sha256=saved["manifest"]["manifest_payload_sha256"])
        for role, artifact in original["scenes"].items():
            assert artifact["sha256"] == restored["scenes"][role]["sha256"]
            assert artifact["artifact_base64"] == restored["scenes"][role]["artifact_base64"]
        assert original["layout"]["layers"].keys() == restored["layout"]["layers"].keys()
        for layer, artifact in original["layout"]["layers"].items():
            assert artifact["artifact_base64"] == restored["layout"]["layers"][layer]["artifact_base64"]
    restored = request("read_project_package", path=str(args.output))
    assert restored["project"]["analysis"] == snapshot["analysis"]
    print(json.dumps({"package": str(args.output), "package_bytes": args.output.stat().st_size,
                      "visual_bytes": sum(item["bytes"] for item in artifacts), "layers": len(responses["layout"]["layout"]["layers"]),
                      "results": len(runs), "source_and_visual_tools_used_on_reopen": False}, indent=2))


if __name__ == "__main__":
    main()
