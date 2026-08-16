import json
from pathlib import Path
from typing import Any

import yaml

from mcp_conductor.entry.main_deploy_dify_workflow import (
    DeploymentConfig,
    deploy,
)


class FakeDifyClient:
    def __init__(self) -> None:
        self.gets: list[tuple[str, dict[str, Any] | None]] = []
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.gets.append((path, params))
        if path.endswith("/workflows/draft"):
            return {"graph": {"nodes": [], "edges": []}, "hash": "draft-hash"}
        if path == "workspaces/current/tool-provider/api/get":
            return {
                "credentials": {"auth_type": "none"},
                "schema_type": "openapi",
                "schema": "{}",
                "icon": {"background": "#fff", "content": "tool"},
                "privacy_policy": "",
                "custom_disclaimer": "",
                "labels": [],
            }
        if path.endswith("/export"):
            return {"data": "kind: app\napp:\n  mode: advanced-chat\nworkflow:\n  graph: {}\n"}
        raise AssertionError(f"Unexpected GET: {path}")

    def get_json_list(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.gets.append((path, params))
        if path == "workspaces/current/tool-providers":
            return [
                {
                    "id": "current-detection-provider-id",
                    "name": "detectanomoly",
                    "type": "api",
                },
                {
                    "id": "current-analysis-provider-id",
                    "name": "analyzeAnomaly",
                    "type": "api",
                },
            ]
        raise AssertionError(f"Unexpected GET list: {path}")

    def post_json(self, path: str, *, body: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((path, body))
        if path == "apps/imports":
            return {"id": "import-id", "status": "completed"}
        if path.endswith("/workflows/publish"):
            return {"result": "success"}
        if path == "workspaces/current/tool-provider/api/update":
            return {"result": "success"}
        raise AssertionError(f"Unexpected POST: {path}")


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        """kind: app
app:
  mode: advanced-chat
workflow:
  graph:
    nodes:
    - data:
        provider_id: stale-detection-provider-id
        provider_name: detectanomoly
    - data:
        provider_id: stale-analysis-provider-id
        provider_name: analyzeAnomaly
""",
        encoding="utf-8",
    )
    schema = {"openapi": "3.1.0", "paths": {"/detect": {"post": {}}}}
    detection_schema = tmp_path / "detect.json"
    detection_schema.write_text(json.dumps(schema), encoding="utf-8")
    analysis_schema = tmp_path / "analyze.json"
    analysis_schema.write_text(json.dumps(schema), encoding="utf-8")
    return workflow, detection_schema, analysis_schema


def _config(tmp_path: Path, *, apply: bool = False, publish: bool = False) -> DeploymentConfig:
    workflow, detection_schema, analysis_schema = _write_inputs(tmp_path)
    return DeploymentConfig(
        console_api_url="http://dify.test/console/api",
        admin_api_key="a" * 64,
        workspace_id="workspace-id",
        app_id="app-id",
        workflow_dsl=workflow,
        tool_schema=detection_schema,
        tool_provider="detectanomoly",
        analysis_tool_schema=analysis_schema,
        analysis_tool_provider="analyzeAnomaly",
        backup_dir=tmp_path / "backups",
        apply=apply,
        publish=publish,
    )


def test_default_mode_is_read_only(tmp_path):
    client = FakeDifyClient()

    result = deploy(_config(tmp_path), client=client)

    assert result.applied is False
    assert result.published is False
    assert client.posts == []
    assert (
        "workspaces/current/tool-providers",
        {"type": "api"},
    ) in client.gets
    assert [
        params["provider"]
        for path, params in client.gets
        if params and "provider" in params
    ] == [
        "detectanomoly",
        "analyzeAnomaly",
    ]


def test_apply_updates_both_tools_before_explicit_publish(tmp_path):
    client = FakeDifyClient()

    result = deploy(_config(tmp_path, apply=True, publish=True), client=client)

    assert result.applied is True
    assert result.published is True
    assert result.tool_schema_updated is True
    assert result.backup_dir is not None
    assert (result.backup_dir / "workflow.yml").is_file()
    assert (result.backup_dir / "tool-provider-detectanomoly.json").is_file()
    assert (result.backup_dir / "tool-provider-analyzeAnomaly.json").is_file()

    paths = [path for path, _ in client.posts]
    assert paths == [
        "apps/imports",
        "workspaces/current/tool-provider/api/update",
        "workspaces/current/tool-provider/api/update",
        "apps/app-id/workflows/publish",
    ]
    updated_providers = [
        body["provider"]
        for path, body in client.posts
        if path == "workspaces/current/tool-provider/api/update"
    ]
    assert updated_providers == ["detectanomoly", "analyzeAnomaly"]

    imported_workflow = client.posts[0][1]["yaml_content"]
    assert "provider_id: current-detection-provider-id" in imported_workflow
    assert "provider_id: current-analysis-provider-id" in imported_workflow
    assert "stale-detection-provider-id" not in imported_workflow
    assert "stale-analysis-provider-id" not in imported_workflow


def test_route_conditions_use_string_compatible_operator():
    workflow_path = (
        Path(__file__).resolve().parents[3]
        / "mcp_conductor"
        / "resources"
        / "dify"
        / "sisi_expert_chat.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    nodes = workflow["workflow"]["graph"]["nodes"]
    route_node = next(node for node in nodes if node["id"] == "1770528175479")

    for case in route_node["data"]["cases"]:
        condition = case["conditions"][0]
        assert condition["comparison_operator"] == "is"
