"""Read-only resources using the same REST checks as tools."""

import json
from uuid import UUID

from app.mcp.tools import Offset, compact_entry, text_page


def register_resources(server, rest):
    @server.resource("voicevault://entries/{entry_id}", mime_type="application/json")
    async def entry_metadata(entry_id: UUID) -> str:
        """Entry metadata and links to text resources; requires entries:read."""
        return json.dumps(
            compact_entry(await rest.request("GET", f"/api/entries/{entry_id}")),
        )

    async def read_text(entry_id, field, offset=0):
        return json.dumps(
            text_page(
                await rest.request("GET", f"/api/entries/{entry_id}"),
                field,
                offset,
            ),
        )

    @server.resource(
        "voicevault://entries/{entry_id}/transcript",
        mime_type="application/json",
    )
    async def transcript(entry_id: UUID) -> str:
        """First transcript page, with next_uri when more text is available."""
        return await read_text(entry_id, "transcript")

    @server.resource(
        "voicevault://entries/{entry_id}/transcript/{offset}",
        mime_type="application/json",
    )
    async def transcript_page(entry_id: UUID, offset: Offset) -> str:
        """Transcript continuation, offset measured in characters."""
        return await read_text(entry_id, "transcript", offset)

    @server.resource(
        "voicevault://entries/{entry_id}/summary",
        mime_type="application/json",
    )
    async def summary(entry_id: UUID) -> str:
        """Saved summary only; never generates or changes it. Includes next_uri if needed."""
        return await read_text(entry_id, "summary")

    @server.resource(
        "voicevault://entries/{entry_id}/summary/{offset}",
        mime_type="application/json",
    )
    async def summary_page(entry_id: UUID, offset: Offset) -> str:
        """Saved summary continuation, offset measured in characters."""
        return await read_text(entry_id, "summary", offset)

    @server.resource("voicevault://projects/{project_id}", mime_type="application/json")
    async def project(project_id: UUID) -> str:
        """Project details; requires projects:read and project access."""
        return json.dumps(await rest.request("GET", f"/api/projects/{project_id}"))
