# Obsidian MCP Permissions And Web UI Design

Date: 2026-06-12

## Decision

Add single-user local permission profiles and a FastAPI-backed Web UI. Permissions are enforced in backend services and API routes. The Web UI reflects the active policy but is not trusted as the enforcement boundary.

## Goals

- Add local single-user permission profiles:
  - `read_only`
  - `safe_write`
  - `admin`
- Enforce permissions for core and knowledge actions.
- Add a local FastAPI Web UI for notes, search, knowledge tools, graph/dashboard actions, and permission visibility.
- Serve static HTML/CSS/JS from the Python app.
- Keep the implementation deterministic and local.

## Non-Goals

- No multi-user login.
- No password auth.
- No sessions or JWTs.
- No remote access hardening.
- No database-backed users or roles.
- No React/Vite frontend build system in this stage.

## Permission Model

The permission model is a local policy profile selected by configuration or API state.

### Profiles

- `read_only`: allows read, search, list, metadata, graph, duplicate detection, suggestion, and preview-style operations.
- `safe_write`: allows read operations plus create, update, append, MOC creation, atomic note creation, dashboard generation, and Excalidraw generation.
- `admin`: allows all operations, including delete, move, rename, and refactor operations that create notes.

### Enforcement

Permission checks happen in a shared `PermissionService`. API routes and future MCP wrappers can call the same service before executing actions. The UI must disable blocked controls, but backend policy remains authoritative.

## Web API

Add `obsidian_mcp.web.app` with an app factory:

- `create_web_app(settings: ObsidianMCPSettings) -> FastAPI`

Initial routes:

- `GET /api/status`
- `GET /api/permissions/profile`
- `PUT /api/permissions/profile`
- `GET /api/notes`
- `GET /api/notes/{path:path}`
- `PUT /api/notes/{path:path}`
- `GET /api/search`
- `POST /api/tools/build-moc`
- `POST /api/tools/create-atomic-note`
- `GET /api/tools/relationship-graph`
- `POST /api/tools/dataview-dashboard`
- `GET /`
- static assets under `/static`

## Web UI

The UI is a quiet operational interface, not a marketing page.

Layout:

- Top bar: vault name, active profile selector, server status.
- Left rail: Notes, Search, Knowledge, Graph, Dashboards, Permissions.
- Main workspace:
  - Notes: file list, preview/editor, save action.
  - Search: query input and ranked results.
  - Knowledge: MOC, atomic note, auto-tag, backlink suggestions.
  - Graph: relationship graph JSON preview.
  - Dashboards: Dataview dashboard generator.
  - Permissions: active profile and allowed/blocked action summary.

Accessibility:

- Semantic HTML.
- Labels for inputs.
- Buttons use text labels and disabled states.
- No emoji icons.
- No hardcoded one-off inline styles in production UI assets.

## Configuration

Add settings:

- `permission_profile`: default `safe_write`.
- `web_host`: default `127.0.0.1`.
- `web_port`: default `8765`.

## Testing

Tests remain under `_test_`.

Coverage:

- Permission profile allow/deny matrix.
- Profile validation.
- API status and permission routes.
- API note update denial in `read_only`.
- API note update allowed in `safe_write`.
- Static UI route serves HTML.

## Documentation

Update:

- `DOCS/AICONTEXT.md`
- `DOCS/codebase_reference.md`
- `DOCS/features/permissions-and-web-ui.md`
- `README.md`
- `agent_logs.md`

## Future Extension Points

Multi-user auth, persistent permission storage, CSRF hardening, remote deployment configuration, and a React/Vite UI remain future work.
