import os
import sys
from pathlib import Path
from unittest import TestCase

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.capabilities import (
    CATALOG,
    DEFAULT_EVERYONE,
    PROJECT_SCOPED,
    ROUTE_POLICY,
    TOOL_POLICY,
    Capability,
    normalize_token_capabilities,
)


class CatalogTests(TestCase):
    def test_every_capability_is_described(self):
        self.assertEqual(set(CATALOG), set(Capability))

    def test_global_only_capabilities(self):
        for cap in (
            Capability.PROJECTS_CREATE,
            Capability.TOKENS_CREATE,
            Capability.MCP_CONNECT,
            Capability.TEMPLATES_MANAGE,
            Capability.ADMIN_VIEW,
        ):
            self.assertNotIn(cap, PROJECT_SCOPED)
        self.assertIn(Capability.ENTRIES_CHAT, PROJECT_SCOPED)

    def test_everyone_default_matches_previous_behaviour(self):
        self.assertNotIn(Capability.ADMIN_VIEW, DEFAULT_EVERYONE)
        self.assertNotIn(Capability.ADMIN_MANAGE, DEFAULT_EVERYONE)
        self.assertNotIn(Capability.TEMPLATES_MANAGE, DEFAULT_EVERYONE)
        self.assertIn(Capability.MCP_CONNECT, DEFAULT_EVERYONE)


class TokenCapabilityTests(TestCase):
    def test_new_names_pass_through_sorted_and_unique(self):
        self.assertEqual(
            normalize_token_capabilities(
                ["entries.view", "entries.chat", "entries.view"],
            ),
            ["entries.chat", "entries.view"],
        )

    def test_legacy_scopes_are_converted_and_gain_mcp(self):
        self.assertEqual(
            normalize_token_capabilities(["entries:read"]),
            ["entries.chat", "entries.export", "entries.view", "mcp.connect"],
        )
        self.assertIn(
            "entries.summarize",
            normalize_token_capabilities(["entries:write"]),
        )
        self.assertEqual(
            normalize_token_capabilities(["admin:read"]),
            ["admin.view", "mcp.connect"],
        )

    def test_unknown_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown capability: nope"):
            normalize_token_capabilities(["nope"])


class PolicyCoverageTests(TestCase):
    """Every route and tool is in the rule book, and the rule book has no
    leftovers - a new route cannot slip through unprotected."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("LLM_BASE_URL", "http://llm.invalid/v1")
        os.environ.setdefault("LLM_MODEL", "test")
        from fastapi.routing import APIRoute

        from app.main import app

        cls.routes = {
            (method, route.path_format)
            for route in app.routes
            if isinstance(route, APIRoute) and route.path_format.startswith("/api")
            for method in route.methods
        }

    def test_every_route_is_mapped(self):
        missing = sorted(self.routes - set(ROUTE_POLICY))
        self.assertEqual(missing, [], f"routes missing from ROUTE_POLICY: {missing}")

    def test_no_stale_route_rules(self):
        stale = sorted(
            key
            for key in set(ROUTE_POLICY) - self.routes
            # OAuth consent routes are only mounted when OAuth is active.
            if not key[1].startswith("/api/oauth/")
        )
        self.assertEqual(stale, [], f"ROUTE_POLICY rules without a route: {stale}")

    def test_every_mcp_tool_is_mapped(self):
        from app.mcp.tools import register_tools

        names = []

        class Recorder:
            def tool(self, **kwargs):
                def wrap(fn):
                    names.append(kwargs.get("name") or fn.__name__)
                    return fn

                return wrap

        register_tools(Recorder(), rest=None)
        self.assertEqual(set(names), set(TOOL_POLICY))
