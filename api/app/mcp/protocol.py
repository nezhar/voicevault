"""SDK boundary for literal JSON arguments and safe operation errors."""

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ResourceError, ToolError
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata
from pydantic import ValidationError

from app.mcp.adapter import RESTError


class JSONArgumentsMetadata(FuncMetadata):
    def pre_parse_json(self, data):
        # MCP arguments are already JSON. Decoding strings again changes literal
        # searches such as "null" and "[]". Objects must be sent as JSON objects.
        return data


def safe_error(exc):
    """Find typed failures through SDK wrappers without rendering raw exceptions."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, RESTError):
            return str(exc)  # Already sanitized by the REST adapter.
        if isinstance(exc, ValidationError):
            errors = exc.errors(
                include_input=False,
                include_context=False,
                include_url=False,
            )
            # Error messages can interpolate rejected values (e.g. custom
            # validators); report locations and stable error codes instead.
            details = "; ".join(
                f"{'.'.join(map(str, error['loc'])) or 'arguments'}: {error['type']}"
                for error in errors
            )
            return f"Invalid request parameters: {details}"
        exc = exc.__cause__ or exc.__context__
    return "VoiceVault operation failed"


class VoiceVaultMCP(FastMCP):
    def add_tool(self, fn, name=None, **kwargs):
        super().add_tool(fn, name=name, **kwargs)
        # Keep the SDK's context injection, schemas and result conversion. This
        # internal metadata hook is covered by protocol tests against our pinned SDK.
        tool = self._tool_manager.get_tool(name or fn.__name__)
        metadata = tool.fn_metadata
        tool.fn_metadata = JSONArgumentsMetadata(
            arg_model=metadata.arg_model,
            output_schema=metadata.output_schema,
            output_model=metadata.output_model,
            wrap_output=metadata.wrap_output,
        )

    async def call_tool(self, name, arguments):
        try:
            return await super().call_tool(name, arguments)
        except Exception as exc:
            raise ToolError(safe_error(exc)) from None

    async def read_resource(self, uri):
        try:
            return await super().read_resource(uri)
        except Exception as exc:
            raise ResourceError(safe_error(exc)) from None
