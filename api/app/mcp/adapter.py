"""Internal REST dispatch; credentials never leave this ASGI application."""

import asyncio
from contextvars import ContextVar

import httpx
from mcp.server.fastmcp.exceptions import ToolError

OPERATION_TIMEOUT_SECONDS = 180

# Stateless MCP requests inherit their own context, including concurrent calls.
authorization: ContextVar[str] = ContextVar("mcp_authorization")


class RESTError(ToolError):
    """A safe REST failure with a status usable by the transport layer."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        super().__init__(f"REST {status_code}: {detail}")


class RESTAdapter:
    def __init__(self, app):
        self.app = app

    async def request(self, method: str, path: str, **kwargs):
        # Only module-owned paths reach this method; no client-supplied upstream.
        try:
            async with asyncio.timeout(OPERATION_TIMEOUT_SECONDS):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(
                        app=self.app,
                        raise_app_exceptions=False,
                    ),
                    base_url="http://voicevault.internal",
                    headers={"Authorization": authorization.get()},
                    follow_redirects=False,
                ) as client:
                    response = await client.request(method, path, **kwargs)
        except (TimeoutError, httpx.HTTPError):
            raise RESTError(
                503,
                "VoiceVault is unavailable; check the operation before retrying",
            ) from None
        if response.is_error:
            detail = "VoiceVault request failed"
            if response.status_code < 500:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                value = payload.get("detail") if isinstance(payload, dict) else None
                # Validation errors include the submitted input; don't echo it.
                detail = (
                    value if isinstance(value, str) else "Invalid request parameters"
                )
            raise RESTError(response.status_code, detail)
        if response.is_redirect:
            raise RESTError(502, "Unexpected upstream redirect")
        try:
            return response.json()
        except ValueError:
            raise RESTError(502, "Invalid response from VoiceVault") from None
