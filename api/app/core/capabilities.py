"""What a user, group or token may do: the capability catalog and the rule book.

Capabilities gate features. Which content someone can reach is decided
separately by ownership and project membership (app/services/authz.py); a
capability never makes a project visible.

ROUTE_POLICY lists every /api route and TOOL_POLICY every MCP tool. Anything not
listed is refused to personal access tokens, so a new route cannot become
token-callable by accident; tests keep both lists in step with the app.
"""

from dataclasses import dataclass
from enum import Enum


class Capability(str, Enum):
    ENTRIES_VIEW = "entries.view"
    ENTRIES_UPLOAD = "entries.upload"
    ENTRIES_IMPORT_URL = "entries.import_url"
    ENTRIES_IMPORT_TRANSCRIPT = "entries.import_transcript"
    ENTRIES_EDIT = "entries.edit"
    ENTRIES_DELETE = "entries.delete"
    ENTRIES_CHAT = "entries.chat"
    ENTRIES_SUMMARIZE = "entries.summarize"
    ENTRIES_EXPORT = "entries.export"
    PROJECTS_CREATE = "projects.create"
    PROJECTS_MANAGE = "projects.manage"
    TEMPLATES_USE = "templates.use"
    TEMPLATES_MANAGE = "templates.manage"
    TOKENS_CREATE = "tokens.create"
    MCP_CONNECT = "mcp.connect"
    ADMIN_VIEW = "admin.view"
    ADMIN_MANAGE = "admin.manage"


@dataclass(frozen=True)
class CapabilityInfo:
    label: str
    area: str
    description: str
    project_scoped: bool


CATALOG: dict[Capability, CapabilityInfo] = {
    Capability.ENTRIES_VIEW: CapabilityInfo(
        "View entries",
        "Entries",
        "List and open entries: transcript, summary and audio.",
        True,
    ),
    Capability.ENTRIES_UPLOAD: CapabilityInfo(
        "Upload files",
        "Entries",
        "Upload audio and video files, also through upload links.",
        True,
    ),
    Capability.ENTRIES_IMPORT_URL: CapabilityInfo(
        "Import from URL",
        "Entries",
        "Create entries from a video or audio URL.",
        True,
    ),
    Capability.ENTRIES_IMPORT_TRANSCRIPT: CapabilityInfo(
        "Import transcripts",
        "Entries",
        "Create entries from an existing transcript.",
        True,
    ),
    Capability.ENTRIES_EDIT: CapabilityInfo(
        "Edit entries",
        "Entries",
        "Change metadata and status, archive, move between projects.",
        True,
    ),
    Capability.ENTRIES_DELETE: CapabilityInfo(
        "Delete entries",
        "Entries",
        "Permanently delete own entries.",
        True,
    ),
    Capability.ENTRIES_EXPORT: CapabilityInfo(
        "Export subtitles",
        "Entries",
        "Download transcripts as SRT files.",
        True,
    ),
    Capability.ENTRIES_CHAT: CapabilityInfo(
        "Chat",
        "AI",
        "Chat with a transcript using the LLM.",
        True,
    ),
    Capability.ENTRIES_SUMMARIZE: CapabilityInfo(
        "Generate summaries",
        "AI",
        "Generate and save AI summaries.",
        True,
    ),
    Capability.PROJECTS_CREATE: CapabilityInfo(
        "Create projects",
        "Projects",
        "Create new projects.",
        False,
    ),
    Capability.PROJECTS_MANAGE: CapabilityInfo(
        "Manage projects",
        "Projects",
        "Settings, members, group shares and access requests "
        "(the owner role is still required).",
        True,
    ),
    Capability.TEMPLATES_USE: CapabilityInfo(
        "Use prompt templates",
        "Templates",
        "List prompt templates and use them in chat.",
        False,
    ),
    Capability.TEMPLATES_MANAGE: CapabilityInfo(
        "Manage prompt templates",
        "Templates",
        "Create, edit and delete the shared prompt templates.",
        False,
    ),
    Capability.TOKENS_CREATE: CapabilityInfo(
        "Create access tokens",
        "Integrations",
        "Create personal access tokens for API clients.",
        False,
    ),
    Capability.MCP_CONNECT: CapabilityInfo(
        "Connect MCP clients",
        "Integrations",
        "Use the MCP endpoint and approve OAuth sign-ins of MCP clients.",
        False,
    ),
    Capability.ADMIN_VIEW: CapabilityInfo(
        "View administration",
        "Admin",
        "Platform statistics, users and their permissions.",
        False,
    ),
    Capability.ADMIN_MANAGE: CapabilityInfo(
        "Manage administration",
        "Admin",
        "Activate users, manage groups, grants and every user's tokens.",
        False,
    ),
}

ALL_CAPABILITIES = frozenset(Capability)
PROJECT_SCOPED = frozenset(cap for cap, info in CATALOG.items() if info.project_scoped)

# What the built-in Everyone group holds on a fresh install or upgrade: what
# every signed-in user could do before capabilities existed.
DEFAULT_EVERYONE = ALL_CAPABILITIES - {
    Capability.ADMIN_VIEW,
    Capability.ADMIN_MANAGE,
    Capability.TEMPLATES_MANAGE,
}


class Marker(str, Enum):
    PUBLIC = "public"  # no authentication at all
    OPEN = "open"  # any authenticated caller, tokens included
    INTERACTIVE = "interactive"  # browser session or shared token; never a PAT
    LINK = "link"  # authenticated by an upload-link token only


Rule = Capability | Marker

C = Capability
ROUTE_POLICY: dict[tuple[str, str], Rule] = {
    ("POST", "/api/auth/login"): Marker.PUBLIC,
    ("POST", "/api/auth/verify"): Marker.PUBLIC,
    ("GET", "/api/auth/config"): Marker.PUBLIC,
    ("POST", "/api/auth/logout"): Marker.PUBLIC,
    ("GET", "/api/auth/oidc/login"): Marker.PUBLIC,
    ("GET", "/api/auth/oidc/callback"): Marker.PUBLIC,
    ("GET", "/api/auth/me"): Marker.OPEN,
    ("GET", "/api/capabilities"): Marker.OPEN,
    ("POST", "/api/auth/pats"): Marker.INTERACTIVE,
    ("GET", "/api/auth/pats"): Marker.INTERACTIVE,
    ("PATCH", "/api/auth/pats/{token_id}"): Marker.INTERACTIVE,
    ("DELETE", "/api/auth/pats/{token_id}"): Marker.INTERACTIVE,
    ("POST", "/api/entries/upload-sessions"): C.ENTRIES_UPLOAD,
    ("GET", "/api/entries/upload-sessions/{session_id}"): C.ENTRIES_VIEW,
    ("GET", "/api/uploads/{session_id}"): Marker.LINK,
    ("PUT", "/api/uploads/{session_id}"): Marker.LINK,
    ("POST", "/api/entries/upload"): C.ENTRIES_UPLOAD,
    ("POST", "/api/entries/url"): C.ENTRIES_IMPORT_URL,
    ("POST", "/api/entries/transcript"): C.ENTRIES_IMPORT_TRANSCRIPT,
    ("GET", "/api/entries/"): C.ENTRIES_VIEW,
    ("GET", "/api/entries/{entry_id}"): C.ENTRIES_VIEW,
    ("PUT", "/api/entries/{entry_id}/status"): C.ENTRIES_EDIT,
    ("PUT", "/api/entries/{entry_id}/metadata"): C.ENTRIES_EDIT,
    ("PUT", "/api/entries/{entry_id}/archive"): C.ENTRIES_EDIT,
    ("DELETE", "/api/entries/{entry_id}"): C.ENTRIES_DELETE,
    ("PUT", "/api/entries/{entry_id}/project"): C.ENTRIES_EDIT,
    ("POST", "/api/entries/{entry_id}/chat"): C.ENTRIES_CHAT,
    ("GET", "/api/entries/{entry_id}/audio"): C.ENTRIES_VIEW,
    ("GET", "/api/entries/{entry_id}/subtitles"): C.ENTRIES_EXPORT,
    ("POST", "/api/entries/{entry_id}/summary"): C.ENTRIES_SUMMARIZE,
    ("GET", "/api/prompt-templates/"): C.TEMPLATES_USE,
    ("POST", "/api/prompt-templates/"): C.TEMPLATES_MANAGE,
    ("PUT", "/api/prompt-templates/{template_id}"): C.TEMPLATES_MANAGE,
    ("DELETE", "/api/prompt-templates/{template_id}"): C.TEMPLATES_MANAGE,
    ("POST", "/api/projects/"): C.PROJECTS_CREATE,
    ("GET", "/api/projects/"): Marker.OPEN,
    ("GET", "/api/projects/{project_id}"): Marker.OPEN,
    ("GET", "/api/projects/{project_id}/preview"): Marker.OPEN,
    ("PUT", "/api/projects/{project_id}"): C.PROJECTS_MANAGE,
    ("DELETE", "/api/projects/{project_id}"): C.PROJECTS_MANAGE,
    ("POST", "/api/projects/{project_id}/members"): C.PROJECTS_MANAGE,
    ("PUT", "/api/projects/{project_id}/members/{user_id}"): C.PROJECTS_MANAGE,
    # Leaving a project is open; removing others is checked in the route.
    ("DELETE", "/api/projects/{project_id}/members/{user_id}"): Marker.OPEN,
    ("POST", "/api/projects/{project_id}/groups"): C.PROJECTS_MANAGE,
    ("PUT", "/api/projects/{project_id}/groups/{group_id}"): C.PROJECTS_MANAGE,
    ("DELETE", "/api/projects/{project_id}/groups/{group_id}"): C.PROJECTS_MANAGE,
    ("POST", "/api/projects/{project_id}/access-requests"): Marker.OPEN,
    ("DELETE", "/api/projects/{project_id}/access-requests/{request_id}"): Marker.OPEN,
    ("GET", "/api/projects/{project_id}/access-requests"): C.PROJECTS_MANAGE,
    (
        "POST",
        "/api/projects/{project_id}/access-requests/{request_id}/approve",
    ): C.PROJECTS_MANAGE,
    (
        "POST",
        "/api/projects/{project_id}/access-requests/{request_id}/deny",
    ): C.PROJECTS_MANAGE,
    ("GET", "/api/groups/"): C.PROJECTS_MANAGE,
    ("GET", "/api/admin/stats"): C.ADMIN_VIEW,
    ("GET", "/api/admin/users"): C.ADMIN_VIEW,
    ("GET", "/api/admin/users/{user_id}/effective"): Marker.INTERACTIVE,
    ("PATCH", "/api/admin/users/{user_id}/active"): Marker.INTERACTIVE,
    ("GET", "/api/admin/pat-users"): Marker.INTERACTIVE,
    ("GET", "/api/admin/pats"): Marker.INTERACTIVE,
    ("DELETE", "/api/admin/pats/{token_id}"): Marker.INTERACTIVE,
    ("GET", "/api/admin/groups"): Marker.INTERACTIVE,
    ("POST", "/api/admin/groups"): Marker.INTERACTIVE,
    ("GET", "/api/admin/groups/{group_id}"): Marker.INTERACTIVE,
    ("PUT", "/api/admin/groups/{group_id}"): Marker.INTERACTIVE,
    ("DELETE", "/api/admin/groups/{group_id}"): Marker.INTERACTIVE,
    ("POST", "/api/admin/groups/{group_id}/members"): Marker.INTERACTIVE,
    ("DELETE", "/api/admin/groups/{group_id}/members/{user_id}"): Marker.INTERACTIVE,
    ("GET", "/api/admin/projects"): Marker.INTERACTIVE,
    ("GET", "/api/admin/grants"): Marker.INTERACTIVE,
    ("PUT", "/api/admin/grants"): Marker.INTERACTIVE,
    ("GET", "/api/oauth/requests/{request_id}"): Marker.INTERACTIVE,
    ("POST", "/api/oauth/requests/{request_id}/approve"): Marker.INTERACTIVE,
    ("POST", "/api/oauth/requests/{request_id}/deny"): Marker.INTERACTIVE,
}

# None: the tool needs no capability (it lists what the caller can already reach).
TOOL_POLICY: dict[str, Capability | None] = {
    "list_entries": C.ENTRIES_VIEW,
    "get_entry": C.ENTRIES_VIEW,
    "read_entry_text": C.ENTRIES_VIEW,
    "create_entry_from_url": C.ENTRIES_IMPORT_URL,
    "create_entry_from_transcript": C.ENTRIES_IMPORT_TRANSCRIPT,
    "upload_file": C.ENTRIES_UPLOAD,
    "get_upload_status": C.ENTRIES_VIEW,
    "update_entry_metadata": C.ENTRIES_EDIT,
    "update_entry_status": C.ENTRIES_EDIT,
    "set_entry_archived": C.ENTRIES_EDIT,
    "move_entry_to_project": C.ENTRIES_EDIT,
    "delete_entry": C.ENTRIES_DELETE,
    "chat_with_entry": C.ENTRIES_CHAT,
    "generate_entry_summary": C.ENTRIES_SUMMARIZE,
    "list_projects": None,
    "get_project": None,
    "list_prompt_templates": C.TEMPLATES_USE,
}

# Token scopes from before capabilities existed. A converted token also gains
# mcp.connect, because every token could use /mcp back then.
LEGACY_SCOPES: dict[str, tuple[Capability, ...]] = {
    "entries:read": (C.ENTRIES_VIEW, C.ENTRIES_CHAT, C.ENTRIES_EXPORT),
    "entries:write": (
        C.ENTRIES_UPLOAD,
        C.ENTRIES_IMPORT_URL,
        C.ENTRIES_IMPORT_TRANSCRIPT,
        C.ENTRIES_EDIT,
        C.ENTRIES_DELETE,
        C.ENTRIES_SUMMARIZE,
    ),
    "projects:read": (),
    "projects:write": (C.PROJECTS_CREATE, C.PROJECTS_MANAGE),
    "templates:read": (C.TEMPLATES_USE,),
    "templates:write": (C.TEMPLATES_MANAGE,),
    "admin:read": (C.ADMIN_VIEW,),
}


def is_legacy(values) -> bool:
    return any(value in LEGACY_SCOPES for value in values)


def normalize_token_capabilities(values) -> list[str]:
    """Capability names for a token, accepting the old scope names too.

    Raises ValueError naming the first unknown value.
    """

    result: set[str] = set()
    legacy = False
    for value in values:
        value = getattr(value, "value", value)
        if value in LEGACY_SCOPES:
            legacy = True
            result.update(cap.value for cap in LEGACY_SCOPES[value])
            continue
        try:
            result.add(Capability(value).value)
        except ValueError:
            raise ValueError(f"Unknown capability: {value}") from None
    if legacy:
        result.add(C.MCP_CONNECT.value)
    return sorted(result)


def route_rule(method: str, path_format: str) -> Rule | None:
    return ROUTE_POLICY.get((method.upper(), path_format))
