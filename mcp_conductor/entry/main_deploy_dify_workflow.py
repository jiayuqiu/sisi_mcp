"""Deploy the repository's Dify tool schema and workflow DSL.

The current Dify app is used only for read-only preflight checks and rollback
backups. The files under ``mcp_conductor/resources/dify`` are the deployment
inputs.

The command is read-only unless ``--apply`` is supplied. Publishing is a
separate, explicit action.

Examples:
    # Validate local files and verify the remote app/provider (no writes).
    uv run python -m mcp_conductor.entry.main_deploy_dify_workflow \
        --workspace-id 3f2ed995-0fe4-4fbb-96ef-de1e8e3bd418 \
        --app-id 01e1fdf0-1c73-4ea8-b870-5202fa2b7626

    # Back up the current configuration and update the draft.
    uv run python -m mcp_conductor.entry.main_deploy_dify_workflow \
        --workspace-id 3f2ed995-0fe4-4fbb-96ef-de1e8e3bd418 \
        --app-id 01e1fdf0-1c73-4ea8-b870-5202fa2b7626 \
        --apply

    # Update the draft and publish it after both deployment steps succeed.
    uv run python -m mcp_conductor.entry.main_deploy_dify_workflow \
        --workspace-id 3f2ed995-0fe4-4fbb-96ef-de1e8e3bd418 \
        --app-id 01e1fdf0-1c73-4ea8-b870-5202fa2b7626 \
        --apply --publish

Authentication:
    The admin key is read from ``DIFY_ADMIN_API_KEY`` or ``ADMIN_API_KEY``.
    By default the command loads ``dify/docker/.env`` without overriding
    variables already present in the process environment. Use ``--env-file``
    to select another file.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / "dify" / "docker" / ".env"
DEFAULT_WORKFLOW_DSL = PROJECT_ROOT / "mcp_conductor" / "resources" / "dify" / "sisi_expert_chat.yml"
DEFAULT_TOOL_SCHEMA = (
    PROJECT_ROOT / "mcp_conductor" / "resources" / "dify" / "detect_traffic_congestion.json"
)
DEFAULT_ANALYSIS_TOOL_SCHEMA = (
    PROJECT_ROOT / "mcp_conductor" / "resources" / "dify" / "analyze_anomaly_traffic.json"
)
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "backups" / "dify"
DEFAULT_CONSOLE_API_URL = "http://localhost:7080/console/api"
DEFAULT_TOOL_PROVIDER = "detectanomoly"
DEFAULT_ANALYSIS_TOOL_PROVIDER = "analyzeAnomaly"

SUCCESSFUL_IMPORT_STATUSES = {"completed", "completed-with-warnings"}


class DeploymentError(RuntimeError):
    """Raised when preflight or deployment cannot complete safely."""


@dataclass(frozen=True)
class DeploymentConfig:
    console_api_url: str
    admin_api_key: str = field(repr=False)
    workspace_id: str
    app_id: str
    workflow_dsl: Path
    tool_schema: Path
    tool_provider: str
    analysis_tool_schema: Path
    analysis_tool_provider: str
    backup_dir: Path
    timeout: float = 60.0
    apply: bool = False
    publish: bool = False
    confirm_version_mismatch: bool = False
    skip_tool_schema: bool = False
    marked_name: str = "duration-aware"
    marked_comment: str = "Deploy duration-aware traffic detection workflow"


@dataclass(frozen=True)
class DeploymentResult:
    applied: bool
    published: bool
    workflow_status: str
    tool_schema_updated: bool
    backup_dir: Path | None = None


class DifyConsoleClient:
    """Small client for the version-coupled Dify Console API."""

    def __init__(
        self,
        *,
        console_api_url: str,
        admin_api_key: str,
        workspace_id: str,
        timeout: float,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = console_api_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {admin_api_key}",
                "X-WORKSPACE-ID": workspace_id,
                "Content-Type": "application/json",
            }
        )

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._request_json_value("GET", path, params=params)
        if not isinstance(data, dict):
            raise DeploymentError(f"Dify returned an unexpected JSON value for GET {path}")
        return data

    def get_json_list(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        data = self._request_json_value("GET", path, params=params)
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise DeploymentError(f"Dify returned an unexpected JSON value for GET {path}")
        return data

    def post_json(self, path: str, *, body: dict[str, Any]) -> dict[str, Any]:
        data = self._request_json_value("POST", path, body=body)
        if not isinstance(data, dict):
            raise DeploymentError(f"Dify returned an unexpected JSON value for POST {path}")
        return data

    def _request_json_value(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise DeploymentError(f"Dify request failed: {method} {url}: {exc}") from exc

        if not response.ok:
            body_preview = (response.text or "")[:1000]
            raise DeploymentError(
                f"Dify returned HTTP {response.status_code} for {method} {url}: {body_preview}"
            )

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise DeploymentError(f"Dify returned non-JSON data for {method} {url}") from exc
        return data


def _read_workflow_dsl(path: Path) -> str:
    if not path.is_file():
        raise DeploymentError(f"Workflow DSL not found: {path}")
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise DeploymentError(f"Workflow DSL is empty: {path}")

    # Avoid a new YAML dependency while still catching common wrong-file mistakes.
    required_markers = ("kind: app", "workflow:", "mode: advanced-chat")
    missing = [marker for marker in required_markers if marker not in content]
    if missing:
        raise DeploymentError(
            f"Workflow DSL {path} is missing expected marker(s): {', '.join(missing)}"
        )
    return content


def _read_tool_schema(path: Path) -> str:
    if not path.is_file():
        raise DeploymentError(f"Tool schema not found: {path}")
    content = path.read_text(encoding="utf-8")
    try:
        schema = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DeploymentError(f"Tool schema is not valid JSON: {path}: {exc}") from exc

    if not isinstance(schema, dict):
        raise DeploymentError(f"Tool schema must contain a JSON object: {path}")
    if not schema.get("openapi") or not isinstance(schema.get("paths"), dict):
        raise DeploymentError(f"Tool schema does not look like an OpenAPI document: {path}")
    if not schema["paths"]:
        raise DeploymentError(f"Tool schema contains no paths: {path}")
    return content


def _bind_api_provider_ids(workflow_dsl: str, provider_ids: dict[str, str]) -> str:
    """Replace environment-specific API-tool UUIDs immediately before import."""
    bound_dsl = workflow_dsl
    for provider_name, provider_id in provider_ids.items():
        pattern = re.compile(
            rf"(?m)^(?P<indent>[ \t]*)provider_id:\s*[^\r\n]+\r?\n"
            rf"(?P=indent)provider_name:\s*{re.escape(provider_name)}\s*$"
        )

        def replace_provider(match: re.Match[str]) -> str:
            indent = match.group("indent")
            return (
                f"{indent}provider_id: {provider_id}\n"
                f"{indent}provider_name: {provider_name}"
            )

        bound_dsl, replacement_count = pattern.subn(replace_provider, bound_dsl)
        if replacement_count == 0:
            raise DeploymentError(
                f"Workflow DSL has no API-tool node for provider {provider_name!r}"
            )
        logger.info(
            "Bound %d workflow tool node(s) to provider=%s id=%s",
            replacement_count,
            provider_name,
            provider_id,
        )
    return bound_dsl


def _preflight(
    client: DifyConsoleClient,
    config: DeploymentConfig,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    draft = client.get_json(f"apps/{config.app_id}/workflows/draft")
    if not isinstance(draft.get("graph"), dict):
        raise DeploymentError("The target app did not return a valid draft workflow graph")

    provider_names = (config.tool_provider, config.analysis_tool_provider)
    provider_list = client.get_json_list(
        "workspaces/current/tool-providers",
        params={"type": "api"},
    )
    provider_ids: dict[str, str] = {}
    for provider_name in provider_names:
        matches = [item for item in provider_list if item.get("name") == provider_name]
        if len(matches) != 1:
            raise DeploymentError(
                f"Expected exactly one API tool provider named {provider_name!r}; found {len(matches)}"
            )
        provider_id = matches[0].get("id")
        if not isinstance(provider_id, str) or not provider_id:
            raise DeploymentError(f"Tool provider {provider_name!r} has no valid provider ID")
        provider_ids[provider_name] = provider_id

    providers: dict[str, dict[str, Any]] = {}
    if not config.skip_tool_schema:
        for provider_name in provider_names:
            provider = client.get_json(
                "workspaces/current/tool-provider/api/get",
                params={"provider": provider_name},
            )
            required_fields = {"credentials", "schema_type", "icon"}
            missing = sorted(required_fields - provider.keys())
            if missing:
                raise DeploymentError(
                    f"Tool provider {provider_name!r} is missing field(s): {', '.join(missing)}"
                )
            providers[provider_name] = provider
    return draft, providers, provider_ids


def _create_backups(
    client: DifyConsoleClient,
    config: DeploymentConfig,
    providers: dict[str, dict[str, Any]],
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = config.backup_dir / f"{config.app_id}-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)

    exported = client.get_json(
        f"apps/{config.app_id}/export",
        params={"include_secret": "false"},
    )
    workflow_backup = exported.get("data")
    if not isinstance(workflow_backup, str) or not workflow_backup.strip():
        raise DeploymentError("Dify did not return workflow DSL for the backup")
    (target / "workflow.yml").write_text(workflow_backup, encoding="utf-8")

    for provider_name, provider in providers.items():
        # Dify returns masked credentials here. The backup is for schema/config
        # rollback and intentionally never writes clear-text credentials.
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in provider_name)
        (target / f"tool-provider-{safe_name}.json").write_text(
            json.dumps(provider, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    logger.info("Created rollback backup: %s", target)
    return target


def _import_workflow(
    client: DifyConsoleClient,
    config: DeploymentConfig,
    workflow_dsl: str,
) -> str:
    result = client.post_json(
        "apps/imports",
        body={
            "mode": "yaml-content",
            "yaml_content": workflow_dsl,
            "app_id": config.app_id,
        },
    )
    status = str(result.get("status", ""))

    if status == "pending":
        imported = result.get("imported_dsl_version", "unknown")
        current = result.get("current_dsl_version", "unknown")
        if not config.confirm_version_mismatch:
            raise DeploymentError(
                "Dify requires confirmation for a DSL version mismatch "
                f"(imported={imported}, current={current}). Re-run with "
                "--confirm-version-mismatch after reviewing the versions."
            )
        import_id = result.get("id")
        if not isinstance(import_id, str) or not import_id:
            raise DeploymentError("Dify returned pending import status without an import ID")
        result = client.post_json(f"apps/imports/{import_id}/confirm", body={})
        status = str(result.get("status", ""))

    if status not in SUCCESSFUL_IMPORT_STATUSES:
        error = result.get("error") or result.get("message") or "unknown import error"
        raise DeploymentError(f"Dify workflow import failed with status {status!r}: {error}")

    logger.info("Updated Dify draft workflow: status=%s", status)
    return status


def _update_tool_schema(
    client: DifyConsoleClient,
    provider_name: str,
    provider: dict[str, Any],
    schema: str,
) -> None:
    client.post_json(
        "workspaces/current/tool-provider/api/update",
        body={
            "provider": provider_name,
            "original_provider": provider_name,
            "credentials": provider["credentials"],
            "schema_type": provider["schema_type"],
            "schema": schema,
            "icon": provider["icon"],
            "privacy_policy": provider.get("privacy_policy") or "",
            "custom_disclaimer": provider.get("custom_disclaimer") or "",
            "labels": provider.get("labels") or [],
        },
    )
    logger.info("Updated Dify custom tool schema: provider=%s", provider_name)


def _publish_workflow(client: DifyConsoleClient, config: DeploymentConfig) -> None:
    client.post_json(
        f"apps/{config.app_id}/workflows/publish",
        body={
            "marked_name": config.marked_name,
            "marked_comment": config.marked_comment,
        },
    )
    logger.info("Published Dify workflow: app_id=%s", config.app_id)


def deploy(
    config: DeploymentConfig,
    *,
    client: DifyConsoleClient | None = None,
) -> DeploymentResult:
    """Validate, preflight, and optionally deploy the workflow and tool schema."""
    if config.publish and not config.apply:
        raise DeploymentError("--publish requires --apply")
    if len(config.marked_name) > 20:
        raise DeploymentError("Publish marked name must be at most 20 characters")
    if len(config.marked_comment) > 100:
        raise DeploymentError("Publish marked comment must be at most 100 characters")

    workflow_dsl = _read_workflow_dsl(config.workflow_dsl)
    tool_schemas = (
        {}
        if config.skip_tool_schema
        else {
            config.tool_provider: _read_tool_schema(config.tool_schema),
            config.analysis_tool_provider: _read_tool_schema(config.analysis_tool_schema),
        }
    )

    active_client = client or DifyConsoleClient(
        console_api_url=config.console_api_url,
        admin_api_key=config.admin_api_key,
        workspace_id=config.workspace_id,
        timeout=config.timeout,
    )
    _, providers, provider_ids = _preflight(active_client, config)
    workflow_dsl = _bind_api_provider_ids(workflow_dsl, provider_ids)

    if not config.apply:
        logger.info("Preflight succeeded; no changes made because --apply was not supplied.")
        return DeploymentResult(
            applied=False,
            published=False,
            workflow_status="not-applied",
            tool_schema_updated=False,
        )

    backup_dir = _create_backups(active_client, config, providers)

    # Import the workflow first. If a DSL version needs confirmation, no tool
    # mutation has occurred yet. Publishing happens only after every update.
    workflow_status = _import_workflow(active_client, config, workflow_dsl)

    tool_schema_updated = False
    for provider_name, schema in tool_schemas.items():
        _update_tool_schema(active_client, provider_name, providers[provider_name], schema)
        tool_schema_updated = True

    if config.publish:
        _publish_workflow(active_client, config)

    return DeploymentResult(
        applied=True,
        published=config.publish,
        workflow_status=workflow_status,
        tool_schema_updated=tool_schema_updated,
        backup_dir=backup_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely deploy a Dify workflow DSL and custom tool schema"
    )
    parser.add_argument(
        "--console-api-url",
        default=os.getenv("DIFY_CONSOLE_API_URL", DEFAULT_CONSOLE_API_URL),
        help=f"Dify Console API base URL (default: {DEFAULT_CONSOLE_API_URL})",
    )
    parser.add_argument(
        "--workspace-id",
        default=os.getenv("DIFY_WORKSPACE_ID"),
        help="Dify workspace ID (or set DIFY_WORKSPACE_ID)",
    )
    parser.add_argument(
        "--app-id",
        default=os.getenv("DIFY_APP_ID"),
        help="Dify app ID (or set DIFY_APP_ID)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"File from which to load ADMIN_API_KEY (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--workflow-dsl",
        type=Path,
        default=DEFAULT_WORKFLOW_DSL,
        help=f"Workflow DSL to deploy (default: {DEFAULT_WORKFLOW_DSL})",
    )
    parser.add_argument(
        "--tool-schema",
        type=Path,
        default=DEFAULT_TOOL_SCHEMA,
        help=f"Custom tool OpenAPI schema (default: {DEFAULT_TOOL_SCHEMA})",
    )
    parser.add_argument(
        "--tool-provider",
        default=DEFAULT_TOOL_PROVIDER,
        help=f"Existing detection-tool provider (default: {DEFAULT_TOOL_PROVIDER})",
    )
    parser.add_argument(
        "--analysis-tool-schema",
        type=Path,
        default=DEFAULT_ANALYSIS_TOOL_SCHEMA,
        help=f"Anomaly-analysis OpenAPI schema (default: {DEFAULT_ANALYSIS_TOOL_SCHEMA})",
    )
    parser.add_argument(
        "--analysis-tool-provider",
        default=DEFAULT_ANALYSIS_TOOL_PROVIDER,
        help=f"Existing anomaly-analysis provider (default: {DEFAULT_ANALYSIS_TOOL_PROVIDER})",
    )
    parser.add_argument(
        "--skip-tool-schema",
        action="store_true",
        help="Deploy only the workflow DSL and leave the custom tool unchanged",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Rollback backup directory (default: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the draft workflow and custom tool updates",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish after all updates succeed; requires --apply",
    )
    parser.add_argument(
        "--confirm-version-mismatch",
        action="store_true",
        help="Confirm a Dify DSL major-version mismatch during import",
    )
    parser.add_argument(
        "--marked-name",
        default="duration-aware",
        help="Published version name (maximum 20 characters)",
    )
    parser.add_argument(
        "--marked-comment",
        default="Deploy duration-aware traffic detection workflow",
        help="Published version comment (maximum 100 characters)",
    )
    return parser


def _config_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> DeploymentConfig:
    if args.env_file:
        load_dotenv(args.env_file, override=False)

    admin_api_key = os.getenv("DIFY_ADMIN_API_KEY") or os.getenv("ADMIN_API_KEY")
    workspace_id = args.workspace_id or os.getenv("DIFY_WORKSPACE_ID")
    app_id = args.app_id or os.getenv("DIFY_APP_ID")

    if not admin_api_key:
        parser.error(
            "DIFY_ADMIN_API_KEY/ADMIN_API_KEY is not set; configure it in the environment or --env-file"
        )
    if admin_api_key == "<paste-generated-token>" or len(admin_api_key) < 32:
        parser.error("The configured Dify admin key is still a placeholder or is too short")
    if not workspace_id:
        parser.error("--workspace-id or DIFY_WORKSPACE_ID is required")
    if not app_id:
        parser.error("--app-id or DIFY_APP_ID is required")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    return DeploymentConfig(
        console_api_url=args.console_api_url,
        admin_api_key=admin_api_key,
        workspace_id=workspace_id,
        app_id=app_id,
        workflow_dsl=args.workflow_dsl,
        tool_schema=args.tool_schema,
        tool_provider=args.tool_provider,
        analysis_tool_schema=args.analysis_tool_schema,
        analysis_tool_provider=args.analysis_tool_provider,
        backup_dir=args.backup_dir,
        timeout=args.timeout,
        apply=args.apply,
        publish=args.publish,
        confirm_version_mismatch=args.confirm_version_mismatch,
        skip_tool_schema=args.skip_tool_schema,
        marked_name=args.marked_name,
        marked_comment=args.marked_comment,
    )


def main(argv: list[str] | None = None) -> DeploymentResult:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _config_from_args(args, parser)
    result = deploy(config)
    logger.info(
        "Deployment result: applied=%s published=%s workflow=%s tool_schema_updated=%s backup=%s",
        result.applied,
        result.published,
        result.workflow_status,
        result.tool_schema_updated,
        result.backup_dir or "none",
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        main()
    except DeploymentError as exc:
        logger.error("Deployment failed: %s", exc)
        raise SystemExit(1) from exc
