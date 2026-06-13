"""FastAPI application for the Obsidian MCP local Web UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from obsidian_mcp.config import ObsidianMCPSettings, AdapterMode
from obsidian_mcp.errors import ApplicationError, PermissionDeniedError
from obsidian_mcp.knowledge.service import KnowledgeService
from obsidian_mcp.permissions import PermissionAction, PermissionProfile, PermissionService
from obsidian_mcp.plugins import (
    DataviewService, ExcalidrawService, OmnisearchService,
    TasksService, TemplaterService,
)
from obsidian_mcp.vault.service import VaultService

STATIC_DIR = Path(__file__).parent / "static"

# ── Request models ────────────────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    profile: PermissionProfile

class NoteContentRequest(BaseModel):
    content: str

class MOCRequest(BaseModel):
    topic: str
    output_path: str | None = None
    limit: int = 20

class AtomicNoteRequest(BaseModel):
    path: str
    title: str
    content: str
    tags: list[str] | None = None
    aliases: list[str] | None = None
    source_links: list[str] | None = None

class DashboardRequest(BaseModel):
    path: str
    title: str
    tags: list[str] | None = None
    folders: list[str] | None = None
    include_tasks: bool = True
    include_recent: bool = True
    include_stats: bool = True

class DataviewFieldsRequest(BaseModel):
    path: str
    fields: dict[str, str]

class TaskCreateRequest(BaseModel):
    note_path: str
    text: str
    due: str | None = None
    scheduled: str | None = None
    priority: str | None = None
    recurrence: str | None = None
    section: str | None = None

class TaskNoteRequest(BaseModel):
    path: str
    title: str
    tasks: list[dict[str, Any]]
    tags: list[str] | None = None
    area: str | None = None

class TaskCompleteRequest(BaseModel):
    note_path: str
    task_text_fragment: str

class TemplateCreateRequest(BaseModel):
    name: str
    template_type: str
    custom_fields: list[str] | None = None
    tags: list[str] | None = None

class TemplateApplyRequest(BaseModel):
    template_name: str
    output_path: str
    variables: dict[str, str] | None = None
    title: str | None = None

class ExcalidrawArchitectureRequest(BaseModel):
    path: str
    title: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, str]]
    layout: str = "layered"

class ExcalidrawConceptMapRequest(BaseModel):
    path: str
    central_concept: str
    branches: list[dict[str, Any]]

class ExcalidrawAnnotateRequest(BaseModel):
    path: str
    text: str
    x: float = 40.0
    y: float = 40.0

class OmnisearchAliasRequest(BaseModel):
    path: str
    aliases: list[str]

class AdapterKeyRequest(BaseModel):
    api_key: str
    host: str = "127.0.0.1"
    port: int = 27123

class RulesUpdateRequest(BaseModel):
    rules: str   # raw multiline text — one rule per line


# ── Factory ───────────────────────────────────────────────────────────

def create_web_app(
    settings: ObsidianMCPSettings,
    vault_service: VaultService | None = None,
) -> FastAPI:
    app = FastAPI(title="Obsidian MCP")

    vault      = vault_service or VaultService(settings.vault_path)
    knowledge  = KnowledgeService(vault)
    dataview   = DataviewService(vault)
    tasks      = TasksService(vault)
    templater  = TemplaterService(vault)
    excalidraw = ExcalidrawService(vault)
    omnisearch = OmnisearchService(vault)

    # Live state (mutable within process)
    _state: dict[str, Any] = {
        "profile": settings.permission_profile,
        "adapter_key": settings.adapter_api_key,
        "adapter_host": settings.adapter_host,
        "adapter_port": settings.adapter_port,
        "rules": _load_rules(),
    }

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ── Helpers ───────────────────────────────────────────────────────

    def _perm() -> PermissionService:
        return PermissionService(_state["profile"])

    def _require(action: PermissionAction) -> None:
        try:
            _perm().require(action)
        except PermissionDeniedError as exc:
            raise HTTPException(status_code=403, detail=exc.to_public_dict()) from exc

    def _call(action: PermissionAction, fn, *args, **kwargs):
        _require(action)
        try:
            return fn(*args, **kwargs)
        except ApplicationError as exc:
            raise HTTPException(status_code=400, detail=exc.to_public_dict()) from exc

    # ── Root ──────────────────────────────────────────────────────────

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    # ── Status ────────────────────────────────────────────────────────

    @app.get("/api/status")
    def status():
        adapter_name = "unknown"
        if hasattr(vault, "_adapter"):
            adapter_name = type(vault._adapter).__name__
        return {
            "server_name": settings.server_name,
            "vault_path": str(settings.vault_path),
            "permission_profile": _state["profile"].value,
            "adapter": adapter_name,
            "adapter_key_set": bool(_state["adapter_key"]),
            "adapter_host": _state["adapter_host"],
            "adapter_port": _state["adapter_port"],
        }

    # ── Settings: REST API key ─────────────────────────────────────────

    @app.get("/api/settings/adapter")
    def get_adapter_settings():
        """Return current adapter config (key masked)."""
        key = _state["adapter_key"]
        masked = ("*" * (len(key) - 4) + key[-4:]) if len(key) > 4 else ("*" * len(key))
        return {
            "key_set": bool(key),
            "key_preview": masked if key else "",
            "host": _state["adapter_host"],
            "port": _state["adapter_port"],
            "mode": settings.adapter_mode.value,
        }

    @app.put("/api/settings/adapter")
    def update_adapter_settings(req: AdapterKeyRequest):
        """Save REST API plugin connection details."""
        _require(PermissionAction.SETTINGS_UPDATE_ADAPTER_KEY)
        _state["adapter_key"]  = req.api_key
        _state["adapter_host"] = req.host
        _state["adapter_port"] = req.port
        # Persist to .env (best-effort)
        _persist_adapter_env(req.api_key, req.host, req.port)
        return {
            "saved": True,
            "key_set": bool(req.api_key),
            "host": req.host,
            "port": req.port,
        }

    @app.post("/api/settings/adapter/test")
    def test_adapter_connection():
        """Probe the configured REST API endpoint."""
        _require(PermissionAction.SETTINGS_UPDATE_ADAPTER_KEY)
        if not _state["adapter_key"]:
            return {"reachable": False, "reason": "No API key configured."}
        try:
            from obsidian_mcp.adapters.rest_api import RestApiAdapter
            probe = RestApiAdapter(
                _state["adapter_key"],
                _state["adapter_host"],
                _state["adapter_port"],
            )
            reachable = probe.health_check()
            probe.close()
            return {"reachable": reachable, "reason": "OK" if reachable else "Connection refused."}
        except Exception as exc:
            return {"reachable": False, "reason": str(exc)}

    # ── AI Rules ──────────────────────────────────────────────────────

    @app.get("/api/rules")
    def get_rules():
        """Return current AI rules text."""
        return {"rules": _state["rules"]}

    @app.put("/api/rules")
    def update_rules(req: RulesUpdateRequest):
        """Save AI rules (persisted to .vault-rules file)."""
        _state["rules"] = req.rules
        _persist_rules(req.rules)
        count = len([l for l in req.rules.splitlines() if l.strip()])
        return {"saved": True, "rule_count": count}

    @app.get("/api/rules/system-prompt")
    def rules_system_prompt():
        """Return the full system prompt that gets injected into MCP sessions."""
        return {"system_prompt": _build_system_prompt(_state["rules"])}

    # ── Permissions ───────────────────────────────────────────────────

    @app.get("/api/permissions/profile")
    def get_permission_profile():
        return _perm().summary()

    @app.put("/api/permissions/profile")
    def update_permission_profile(req: ProfileUpdateRequest):
        _state["profile"] = req.profile
        return _perm().summary()

    # ── Notes ─────────────────────────────────────────────────────────

    @app.get("/api/notes")
    def list_notes():
        return _call(PermissionAction.LIST_FILES, vault.list_files)

    @app.get("/api/notes/{path:path}")
    def read_note(path: str):
        return _call(PermissionAction.READ_NOTE, vault.read_note, path)

    @app.put("/api/notes/{path:path}")
    def update_note(path: str, req: NoteContentRequest):
        return _call(PermissionAction.UPDATE_NOTE, vault.update_note, path, req.content)

    @app.get("/api/search")
    def search(q: str, limit: int = 10):
        return _call(PermissionAction.SEARCH_NOTES, vault.search_notes, q, limit)

    # ── Knowledge ─────────────────────────────────────────────────────

    @app.post("/api/tools/build-moc")
    def build_moc(req: MOCRequest):
        return _call(PermissionAction.BUILD_MOC, knowledge.build_moc, req.topic, req.output_path, req.limit)

    @app.post("/api/tools/create-atomic-note")
    def create_atomic_note(req: AtomicNoteRequest):
        return _call(PermissionAction.CREATE_ATOMIC_NOTE, knowledge.create_atomic_note,
                     req.path, req.title, req.content, req.tags, req.aliases, req.source_links)

    @app.get("/api/tools/relationship-graph")
    def relationship_graph():
        return _call(PermissionAction.BUILD_RELATIONSHIP_GRAPH, knowledge.build_relationship_graph)

    # ── Dataview ──────────────────────────────────────────────────────

    @app.get("/api/plugins/dataview/fields/{path:path}")
    def dataview_fields(path: str):
        return _call(PermissionAction.DATAVIEW_EXTRACT_FIELDS, dataview.extract_fields, path)

    @app.post("/api/plugins/dataview/fields")
    def dataview_add_fields(req: DataviewFieldsRequest):
        return _call(PermissionAction.DATAVIEW_ADD_FIELDS, dataview.add_inline_fields, req.path, req.fields)

    @app.post("/api/plugins/dataview/dashboard")
    def dataview_dashboard(req: DashboardRequest):
        return _call(PermissionAction.DATAVIEW_BUILD_DASHBOARD, dataview.build_dashboard,
                     req.path, req.title,
                     folders=req.folders, tags=req.tags,
                     include_tasks=req.include_tasks,
                     include_recent=req.include_recent,
                     include_stats=req.include_stats)

    @app.get("/api/plugins/dataview/query/table")
    def dataview_table_query(fields: str, folder: str = "", where: str = "", sort: str = "", limit: int = 0):
        field_list = [f.strip() for f in fields.split(",") if f.strip()]
        _require(PermissionAction.DATAVIEW_EXTRACT_FIELDS)
        return {"query": dataview.table_query(field_list, from_folder=folder,
                                               where=where or None, sort=sort or None,
                                               limit=limit or None)}

    @app.get("/api/plugins/dataview/query/task")
    def dataview_task_query(folder: str = "", where: str = "!completed", group_by: str = ""):
        _require(PermissionAction.DATAVIEW_EXTRACT_FIELDS)
        return {"query": dataview.task_query(from_folder=folder, where=where, group_by=group_by or None)}

    # ── Tasks ─────────────────────────────────────────────────────────

    @app.get("/api/plugins/tasks/list/{path:path}")
    def tasks_list(path: str, state: str = ""):
        return _call(PermissionAction.TASKS_LIST, tasks.list_tasks, path,
                     **{"state": state} if state else {})

    @app.get("/api/plugins/tasks/aggregate")
    def tasks_aggregate(state: str = "open", folder: str = "", due_before: str = "",
                        priority: str = "", limit: int = 50):
        kwargs: dict[str, Any] = {"state": state or None, "limit": limit}
        if folder:      kwargs["folder"]     = folder
        if due_before:  kwargs["due_before"] = due_before
        if priority:    kwargs["priority"]   = priority
        return _call(PermissionAction.TASKS_AGGREGATE, tasks.aggregate_tasks, **kwargs)

    @app.post("/api/plugins/tasks/create")
    def tasks_create(req: TaskCreateRequest):
        return _call(PermissionAction.TASKS_CREATE, tasks.create_task,
                     req.note_path, req.text,
                     due=req.due, scheduled=req.scheduled,
                     priority=req.priority, recurrence=req.recurrence,
                     section=req.section)

    @app.post("/api/plugins/tasks/complete")
    def tasks_complete(req: TaskCompleteRequest):
        return _call(PermissionAction.TASKS_COMPLETE, tasks.complete_task,
                     req.note_path, req.task_text_fragment)

    @app.post("/api/plugins/tasks/note")
    def tasks_create_note(req: TaskNoteRequest):
        return _call(PermissionAction.TASKS_CREATE_NOTE, tasks.create_task_note,
                     req.path, req.title, req.tasks, tags=req.tags, area=req.area)

    # ── Templater ─────────────────────────────────────────────────────

    @app.get("/api/plugins/templater/list")
    def templater_list():
        return _call(PermissionAction.TEMPLATER_LIST, templater.list_templates)

    @app.get("/api/plugins/templater/read/{path:path}")
    def templater_read(path: str):
        return _call(PermissionAction.TEMPLATER_RENDER, templater.read_template, path)

    @app.post("/api/plugins/templater/apply")
    def templater_apply(req: TemplateApplyRequest):
        return _call(PermissionAction.TEMPLATER_APPLY, templater.apply_template,
                     req.template_name, req.output_path,
                     variables=req.variables, title=req.title)

    @app.post("/api/plugins/templater/create")
    def templater_create(req: TemplateCreateRequest):
        return _call(PermissionAction.TEMPLATER_CREATE, templater.create_template,
                     req.name, req.template_type,
                     custom_fields=req.custom_fields, tags=req.tags)

    # ── Excalidraw ────────────────────────────────────────────────────

    @app.post("/api/plugins/excalidraw/architecture")
    def excalidraw_architecture(req: ExcalidrawArchitectureRequest):
        return _call(PermissionAction.EXCALIDRAW_GENERATE, excalidraw.generate_architecture,
                     req.path, req.title, req.nodes, req.edges, layout=req.layout)

    @app.post("/api/plugins/excalidraw/concept-map")
    def excalidraw_concept_map(req: ExcalidrawConceptMapRequest):
        return _call(PermissionAction.EXCALIDRAW_CONCEPT_MAP, excalidraw.generate_concept_map,
                     req.path, req.central_concept, req.branches)

    @app.get("/api/plugins/excalidraw/parse/{path:path}")
    def excalidraw_parse(path: str):
        return _call(PermissionAction.EXCALIDRAW_PARSE, excalidraw.parse_elements, path)

    @app.post("/api/plugins/excalidraw/annotate")
    def excalidraw_annotate(req: ExcalidrawAnnotateRequest):
        return _call(PermissionAction.EXCALIDRAW_ANNOTATE, excalidraw.add_text_annotation,
                     req.path, req.text, x=req.x, y=req.y)

    # ── Omnisearch ────────────────────────────────────────────────────

    @app.get("/api/plugins/omnisearch/suggest-aliases/{path:path}")
    def omnisearch_suggest_aliases(path: str, limit: int = 5):
        return _call(PermissionAction.OMNISEARCH_SUGGEST_ALIASES,
                     omnisearch.suggest_aliases, path, limit)

    @app.post("/api/plugins/omnisearch/add-aliases")
    def omnisearch_add_aliases(req: OmnisearchAliasRequest):
        return _call(PermissionAction.OMNISEARCH_ADD_ALIASES,
                     omnisearch.add_aliases, req.path, req.aliases)

    @app.get("/api/plugins/omnisearch/suggest-keywords/{path:path}")
    def omnisearch_suggest_keywords(path: str, limit: int = 8):
        return _call(PermissionAction.OMNISEARCH_SUGGEST_KEYWORDS,
                     omnisearch.suggest_keywords, path, limit)

    @app.get("/api/plugins/omnisearch/poorly-indexed")
    def omnisearch_poorly_indexed(limit: int = 20):
        return _call(PermissionAction.OMNISEARCH_FIND_POORLY_INDEXED,
                     omnisearch.find_poorly_indexed_notes, limit)

    @app.get("/api/plugins/omnisearch/optimise/{path:path}")
    def omnisearch_optimise(path: str):
        return _call(PermissionAction.OMNISEARCH_OPTIMISE, omnisearch.optimise_note, path)

    return app


# ── Rules persistence helpers ─────────────────────────────────────────

_RULES_FILE = Path(".vault-rules")

_DEFAULT_RULES = """Never delete notes without explicit user confirmation.
Always add frontmatter (title, type, tags, created, status) to new notes.
Do not modify notes inside Archive/ or Templates/ folders unless explicitly asked.
When creating tasks, always include a due date.
Prefer atomic notes — one idea per file.
Always link new notes to at least one existing note or MOC.
Never overwrite existing frontmatter fields without reading them first.
Add at least two tags to every new note.
Use [[wikilinks]] for internal references, not markdown links.
Before bulk operations, confirm scope with the user."""

_PRESET_RULES: dict[str, str] = {
    "homelab": """Store all infrastructure notes under the HomeLab/ folder.
Tag every infrastructure note with #home-lab and a sub-tag like #home-lab/proxmox.
Always include an Architecture section in system notes.
Link new service notes to [[MOC - Home Infrastructure]].
Use the system template for any new service or tool note.""",
    "zettelkasten": """Every note must contain exactly one idea (atomic notes only).
Always assign a unique numeric ID prefix to note filenames.
New notes must link to at least one existing note (no orphans).
Use MOC notes to organise clusters of related ideas.
Tags should be sparse — only add a tag if it describes a meaningful category.""",
    "gtd": """All tasks must have a due date and a priority.
Capture notes go in Inbox/ — do not create notes directly in project folders.
Review notes in Inbox/ and move them during weekly review.
Every project must have a dedicated note with a task list.
Use the project template for all project notes.""",
    "safe": """Never create, update, or delete any file without explicit user instruction.
Do not infer intent — always confirm before writing.
Treat all vault operations as read-only unless the user explicitly says to write.
Never append to existing notes without showing the user what will be added first.""",
}


def _load_rules() -> str:
    """Load rules from .vault-rules file, or return defaults."""
    if _RULES_FILE.exists():
        try:
            return _RULES_FILE.read_text(encoding="utf-8")
        except OSError:
            pass
    return _DEFAULT_RULES


def _persist_rules(rules: str) -> None:
    """Save rules to .vault-rules file."""
    try:
        _RULES_FILE.write_text(rules, encoding="utf-8")
    except OSError:
        pass


def _build_system_prompt(rules: str) -> str:
    """Build the full system prompt injected at the start of each MCP session."""
    active_rules = [r.strip() for r in rules.splitlines() if r.strip() and not r.startswith("#")]
    if not active_rules:
        return "You are an Obsidian vault assistant. No additional rules are configured."
    rules_block = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(active_rules))
    return (
        "You are an Obsidian vault assistant with access to MCP tools that can read "
        "and write notes in the user's vault.\n\n"
        "VAULT RULES — You MUST follow these rules in every action:\n"
        + rules_block
        + "\n\nOnly deviate from these rules if the user explicitly overrides one in their message."
    )


# ── .env persistence helper ───────────────────────────────────────────

def _persist_adapter_env(api_key: str, host: str, port: int) -> None:
    """Best-effort: update OBSIDIAN_MCP_ADAPTER_* lines in .env."""
    env_path = Path(".env")
    updates = {
        "OBSIDIAN_MCP_ADAPTER_API_KEY": api_key,
        "OBSIDIAN_MCP_ADAPTER_HOST": host,
        "OBSIDIAN_MCP_ADAPTER_PORT": str(port),
    }
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        written: set[str] = set()
        new_lines = []
        for line in lines:
            matched = False
            for key, val in updates.items():
                if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                    new_lines.append(f"{key}={val}")
                    written.add(key)
                    matched = True
                    break
            if not matched:
                new_lines.append(line)
        for key, val in updates.items():
            if key not in written:
                new_lines.append(f"{key}={val}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError:
        pass  # Non-fatal — in-memory state already updated
