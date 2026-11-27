"""OAuth sign-in for MCP clients, end to end against the real app and SQLite."""

import base64
import hashlib
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LLM_BASE_URL", "http://llm.invalid/v1")
os.environ.setdefault("LLM_MODEL", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlite_support import sqlite_sessionmaker

from app.api.routes import auth, entries, oauth, projects
from app.core.config import AuthMode, settings
from app.db.database import get_db
from app.mcp.server import install_mcp
from app.models.capability_grant import CapabilityGrant
from app.models.entry import Entry, EntryStatus, SourceType
from app.models.group import Group
from app.models.personal_access_token import PersonalAccessToken
from app.models.user import User
from app.services.pat_service import PATService
from app.services.permission_service import PermissionService
from app.services.session_service import SESSION_COOKIE_NAME, SessionService

CALLBACK = "http://localhost:8765/callback"
VERIFIER = "a-long-enough-pkce-code-verifier-0123456789abcdef"
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .decode()
    .rstrip("=")
)
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}


class OAuthTestCase(TestCase):
    auth_mode = AuthMode.OIDC

    def setUp(self):
        self.Session = sqlite_sessionmaker(self)
        with self.Session() as db:
            alice = User(
                email="alice@test",
                display_name="Alice",
                issuer="i",
                subject="a",
            )
            db.add(alice)
            db.flush()
            self.alice = alice.id
            PermissionService(db).seed_defaults()
            db.add(
                Entry(
                    title="Notes",
                    user_id=alice.id,
                    source_type=SourceType.UPLOAD,
                    status=EntryStatus.READY,
                    transcript="hello",
                ),
            )
            db.commit()

        for name, value in (
            ("auth_mode", self.auth_mode),
            ("mcp_enabled", True),
            ("public_base_url", "https://vv.test"),
            ("mcp_allowed_hosts", "testserver"),
            ("oauth_redirect_uris", "https://claude.ai/api/mcp/auth_callback"),
        ):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        @asynccontextmanager
        async def lifespan(app):
            async with app.state.mcp_server.session_manager.run():
                yield

        self.app = FastAPI(lifespan=lifespan)
        for router, prefix in (
            (auth.router, "auth"),
            (entries.router, "entries"),
            (projects.router, "projects"),
            (oauth.router, "oauth"),
        ):
            self.app.include_router(router, prefix=f"/api/{prefix}")

        def test_db():
            with self.Session() as db:
                yield db

        self.app.dependency_overrides[get_db] = test_db
        install_mcp(self.app, settings, session_factory=self.Session)
        self.client = TestClient(self.app, follow_redirects=False)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    # -- helpers ----------------------------------------------------------

    def sign_in(self, user_id=None):
        with self.Session() as db:
            _, token = SessionService(db).create_session(user_id or self.alice)
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def register(self, redirect_uri=CALLBACK, **extra):
        return self.client.post(
            "/api/oauth/register",
            json={
                "client_name": "Pi",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                **extra,
            },
        )

    def authorize(self, client_id, **extra):
        response = self.client.get(
            "/api/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_challenge": CHALLENGE,
                "code_challenge_method": "S256",
                "state": "xyz",
                **extra,
            },
        )
        self.assertEqual(response.status_code, 302, response.text)
        location = response.headers["location"]
        self.assertTrue(location.startswith("https://vv.test/oauth/consent#"), location)
        return location.split("#", 1)[1]

    def approve(self, request_id, permissions=("entries.view", "mcp.connect"), **extra):
        return self.client.post(
            f"/api/oauth/requests/{request_id}/approve",
            json={"permissions": list(permissions), **extra},
        )

    def token(self, client_id, code, verifier=VERIFIER):
        return self.client.post(
            "/api/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CALLBACK,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )

    def full_flow(self, permissions=("entries.view", "mcp.connect")):
        client_id = self.register().json()["client_id"]
        request_id = self.authorize(client_id)
        self.sign_in()
        redirect = self.approve(request_id, permissions).json()["redirect_to"]
        code = parse_qs(urlsplit(redirect).query)["code"][0]
        self.client.cookies.clear()
        return client_id, code


class OAuthFlowTests(OAuthTestCase):
    def test_discovery_starts_from_the_401(self):
        response = self.client.post(
            "/mcp",
            headers=MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(
            'resource_metadata="https://vv.test/.well-known/oauth-protected-resource/mcp"',
            response.headers["www-authenticate"],
        )
        resource = self.client.get("/.well-known/oauth-protected-resource/mcp").json()
        self.assertEqual(
            resource["authorization_servers"],
            ["https://vv.test/api/oauth"],
        )
        for path in (
            "/.well-known/oauth-authorization-server/api/oauth",
            "/.well-known/oauth-authorization-server",
            "/api/oauth/.well-known/oauth-authorization-server",
        ):
            metadata = self.client.get(path).json()
            self.assertEqual(
                metadata["token_endpoint"],
                "https://vv.test/api/oauth/token",
                path,
            )

    def test_full_sign_in_issues_a_scoped_token_that_works_on_mcp(self):
        client_id = self.register().json()["client_id"]
        request_id = self.authorize(client_id, scope="entries.view mcp.connect")
        self.sign_in()

        info = self.client.get(f"/api/oauth/requests/{request_id}")
        self.assertEqual(info.status_code, 200, info.text)
        self.assertEqual(info.json()["client_name"], "Pi")
        self.assertEqual(info.json()["redirect_uri"], CALLBACK)
        self.assertEqual(
            sorted(info.json()["requested_capabilities"]),
            ["entries.view", "mcp.connect"],
        )
        self.assertEqual(info.headers["cache-control"], "no-store")

        redirect = self.approve(request_id).json()["redirect_to"]
        query = parse_qs(urlsplit(redirect).query)
        self.assertTrue(redirect.startswith(CALLBACK))
        self.assertEqual(query["state"], ["xyz"])
        self.client.cookies.clear()

        issued = self.token(client_id, query["code"][0])
        self.assertEqual(issued.status_code, 200, issued.text)
        body = issued.json()
        self.assertTrue(body["access_token"].startswith("vvpat_"))
        self.assertNotIn("refresh_token", body)
        self.assertEqual(body["expires_in"], 90 * 86400)

        with self.Session() as db:
            pat = db.query(PersonalAccessToken).one()
            self.assertEqual(pat.source, "oauth")
            self.assertEqual(pat.oauth_client_id, client_id)
            self.assertEqual(pat.name, "Pi (OAuth)")
            self.assertEqual(pat.permissions, ["entries.view", "mcp.connect"])

        tools = self.client.post(
            "/mcp",
            headers={**MCP_HEADERS, "Authorization": f"Bearer {body['access_token']}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        self.assertEqual(tools.status_code, 200, tools.text)
        names = {tool["name"] for tool in tools.json()["result"]["tools"]}
        self.assertIn("get_entry", names)
        self.assertNotIn("delete_entry", names)

    def test_a_code_works_once(self):
        client_id, code = self.full_flow()
        self.assertEqual(self.token(client_id, code).status_code, 200)
        replay = self.token(client_id, code)
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(replay.json()["error"], "invalid_grant")

    def test_pkce_mismatch_is_refused(self):
        client_id, code = self.full_flow()
        response = self.token(client_id, code, verifier="x" * 50)
        self.assertEqual(response.status_code, 400)
        with self.Session() as db:
            self.assertEqual(db.query(PersonalAccessToken).count(), 0)

    def test_deny_sends_access_denied(self):
        client_id = self.register().json()["client_id"]
        request_id = self.authorize(client_id)
        self.sign_in()
        redirect = self.client.post(f"/api/oauth/requests/{request_id}/deny").json()
        query = parse_qs(urlsplit(redirect["redirect_to"]).query)
        self.assertEqual(query["error"], ["access_denied"])
        self.assertEqual(query["state"], ["xyz"])
        # decided: the request is gone
        self.assertEqual(
            self.client.get(f"/api/oauth/requests/{request_id}").status_code,
            404,
        )

    def test_redirect_allow_list(self):
        self.assertEqual(self.register("http://127.0.0.1:9999/cb").status_code, 201)
        self.assertEqual(
            self.register("https://claude.ai/api/mcp/auth_callback").status_code,
            201,
        )
        refused = self.register("https://evil.example/cb")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["error"], "invalid_redirect_uri")

    def test_approval_needs_an_interactive_login(self):
        client_id = self.register().json()["client_id"]
        request_id = self.authorize(client_id)
        self.assertEqual(self.approve(request_id).status_code, 401)
        with self.Session() as db:
            _, raw = PATService(db).create(
                user_id=self.alice,
                name="t",
                permissions=["entries.view", "mcp.connect"],
                expires_at=None,
            )
        response = self.client.post(
            f"/api/oauth/requests/{request_id}/approve",
            json={"permissions": ["entries.view", "mcp.connect"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_a_client_gets_no_more_than_its_approver(self):
        client_id = self.register().json()["client_id"]
        request_id = self.authorize(client_id)
        self.sign_in()
        self.assertEqual(
            self.approve(request_id, ("admin.manage", "mcp.connect")).status_code,
            403,
        )
        self.assertEqual(self.approve(request_id, ("entries.view",)).status_code, 422)

    def test_approving_needs_mcp_connect(self):
        with self.Session() as db:
            everyone = db.query(Group).filter(Group.is_builtin.is_(True)).one()
            db.query(CapabilityGrant).filter_by(
                group_id=everyone.id,
                capability="mcp.connect",
            ).delete()
            db.commit()
        client_id = self.register().json()["client_id"]
        request_id = self.authorize(client_id)
        self.sign_in()
        self.assertEqual(
            self.client.get(f"/api/oauth/requests/{request_id}").status_code,
            403,
        )


class OAuthOffTests(OAuthTestCase):
    auth_mode = AuthMode.NONE

    def test_nothing_is_mounted_without_users(self):
        self.assertEqual(self.register().status_code, 404)
        self.assertEqual(
            self.client.get("/.well-known/oauth-protected-resource/mcp").status_code,
            404,
        )
        response = self.client.post(
            "/mcp",
            headers=MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
