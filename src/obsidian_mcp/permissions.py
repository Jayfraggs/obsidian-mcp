"""Local single-user permission profiles for Obsidian MCP operations."""

from enum import StrEnum

from obsidian_mcp.errors import PermissionDeniedError


class PermissionProfile(StrEnum):
    READ_ONLY  = "read_only"
    SAFE_WRITE = "safe_write"
    ADMIN      = "admin"


class PermissionAction(StrEnum):
    # ── Core vault ────────────────────────────────────────────────────
    READ_NOTE                        = "read_note"
    LIST_FILES                       = "list_files"
    LIST_FOLDERS                     = "list_folders"
    SEARCH_NOTES                     = "search_notes"
    BUILD_RELATIONSHIP_GRAPH         = "build_relationship_graph"
    DETECT_DUPLICATES                = "detect_duplicates"
    SUGGEST_BACKLINKS                = "suggest_backlinks"
    AUTO_TAG                         = "auto_tag"
    SUGGEST_PARA_LOCATION            = "suggest_para_location"
    SUGGEST_JOHNNY_DECIMAL_LOCATION  = "suggest_johnny_decimal_location"
    CREATE_NOTE                      = "create_note"
    UPDATE_NOTE                      = "update_note"
    APPEND_NOTE                      = "append_note"
    DELETE_NOTE                      = "delete_note"
    MOVE_NOTE                        = "move_note"
    RENAME_NOTE                      = "rename_note"
    BUILD_MOC                        = "build_moc"
    CREATE_ATOMIC_NOTE               = "create_atomic_note"
    REFACTOR_LARGE_NOTE_CREATE       = "refactor_large_note_create"
    CREATE_DATAVIEW_DASHBOARD        = "create_dataview_dashboard"
    GENERATE_EXCALIDRAW_ARCHITECTURE = "generate_excalidraw_architecture"

    # ── Dataview ──────────────────────────────────────────────────────
    DATAVIEW_EXTRACT_FIELDS          = "dataview_extract_fields"
    DATAVIEW_ADD_FIELDS              = "dataview_add_fields"
    DATAVIEW_BUILD_DASHBOARD         = "dataview_build_dashboard"

    # ── Tasks ─────────────────────────────────────────────────────────
    TASKS_LIST                       = "tasks_list"
    TASKS_AGGREGATE                  = "tasks_aggregate"
    TASKS_CREATE                     = "tasks_create"
    TASKS_COMPLETE                   = "tasks_complete"
    TASKS_CREATE_NOTE                = "tasks_create_note"

    # ── Templater ─────────────────────────────────────────────────────
    TEMPLATER_LIST                   = "templater_list"
    TEMPLATER_RENDER                 = "templater_render"
    TEMPLATER_APPLY                  = "templater_apply"
    TEMPLATER_CREATE                 = "templater_create"

    # ── Excalidraw ────────────────────────────────────────────────────
    EXCALIDRAW_GENERATE              = "excalidraw_generate"
    EXCALIDRAW_CONCEPT_MAP           = "excalidraw_concept_map"
    EXCALIDRAW_PARSE                 = "excalidraw_parse"
    EXCALIDRAW_ANNOTATE              = "excalidraw_annotate"

    # ── Omnisearch ────────────────────────────────────────────────────
    OMNISEARCH_SUGGEST_ALIASES       = "omnisearch_suggest_aliases"
    OMNISEARCH_ADD_ALIASES           = "omnisearch_add_aliases"
    OMNISEARCH_SUGGEST_KEYWORDS      = "omnisearch_suggest_keywords"
    OMNISEARCH_FIND_POORLY_INDEXED   = "omnisearch_find_poorly_indexed"
    OMNISEARCH_OPTIMISE              = "omnisearch_optimise"

    # ── Settings ──────────────────────────────────────────────────────
    SETTINGS_UPDATE_ADAPTER_KEY      = "settings_update_adapter_key"


READ_ACTIONS = frozenset({
    PermissionAction.READ_NOTE,
    PermissionAction.LIST_FILES,
    PermissionAction.LIST_FOLDERS,
    PermissionAction.SEARCH_NOTES,
    PermissionAction.BUILD_RELATIONSHIP_GRAPH,
    PermissionAction.DETECT_DUPLICATES,
    PermissionAction.SUGGEST_BACKLINKS,
    PermissionAction.AUTO_TAG,
    PermissionAction.SUGGEST_PARA_LOCATION,
    PermissionAction.SUGGEST_JOHNNY_DECIMAL_LOCATION,
    # Plugin reads
    PermissionAction.DATAVIEW_EXTRACT_FIELDS,
    PermissionAction.TASKS_LIST,
    PermissionAction.TASKS_AGGREGATE,
    PermissionAction.TEMPLATER_LIST,
    PermissionAction.TEMPLATER_RENDER,
    PermissionAction.EXCALIDRAW_PARSE,
    PermissionAction.OMNISEARCH_SUGGEST_ALIASES,
    PermissionAction.OMNISEARCH_SUGGEST_KEYWORDS,
    PermissionAction.OMNISEARCH_FIND_POORLY_INDEXED,
    PermissionAction.OMNISEARCH_OPTIMISE,
})

SAFE_WRITE_ACTIONS = READ_ACTIONS | frozenset({
    PermissionAction.CREATE_NOTE,
    PermissionAction.UPDATE_NOTE,
    PermissionAction.APPEND_NOTE,
    PermissionAction.BUILD_MOC,
    PermissionAction.CREATE_ATOMIC_NOTE,
    PermissionAction.CREATE_DATAVIEW_DASHBOARD,
    PermissionAction.GENERATE_EXCALIDRAW_ARCHITECTURE,
    # Plugin writes
    PermissionAction.DATAVIEW_ADD_FIELDS,
    PermissionAction.DATAVIEW_BUILD_DASHBOARD,
    PermissionAction.TASKS_CREATE,
    PermissionAction.TASKS_COMPLETE,
    PermissionAction.TASKS_CREATE_NOTE,
    PermissionAction.TEMPLATER_APPLY,
    PermissionAction.TEMPLATER_CREATE,
    PermissionAction.EXCALIDRAW_GENERATE,
    PermissionAction.EXCALIDRAW_CONCEPT_MAP,
    PermissionAction.EXCALIDRAW_ANNOTATE,
    PermissionAction.OMNISEARCH_ADD_ALIASES,
    # Settings: key update is safe_write+ so the UI can save it
    PermissionAction.SETTINGS_UPDATE_ADAPTER_KEY,
})


class PermissionService:
    def __init__(self, profile: PermissionProfile) -> None:
        self.profile = profile

    def is_allowed(self, action: PermissionAction) -> bool:
        if self.profile is PermissionProfile.ADMIN:
            return True
        if self.profile is PermissionProfile.SAFE_WRITE:
            return action in SAFE_WRITE_ACTIONS
        return action in READ_ACTIONS

    def require(self, action: PermissionAction) -> None:
        if not self.is_allowed(action):
            raise PermissionDeniedError(f"Permission profile blocks action: {action.value}")

    def summary(self) -> dict[str, list[str] | str]:
        allowed = sorted(a.value for a in PermissionAction if self.is_allowed(a))
        blocked = sorted(a.value for a in PermissionAction if not self.is_allowed(a))
        return {"profile": self.profile.value, "allowed_actions": allowed, "blocked_actions": blocked}
