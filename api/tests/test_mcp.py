"""Protocol tests against real REST routes, database-backed PATs and access checks."""

import asyncio
import json
import socket
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import UUID

sys.path.append(str(Path(__file__).resolve().parents[1]))

import httpx
import uvicorn
from app.api.routes import auth, entries, projects, prompt_templates
from app.core.config import AuthMode, Settings, settings
from app.core.timeutils import utcnow
from app.db.database import Base, get_db
from app.mcp.server import install_mcp
from app.models.entry import Entry, EntryStatus, SourceType
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User
from app.services.pat_service import ALL_PAT_PERMISSIONS, PATService
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


@compiles(PGUUID, "sqlite")
def sqlite_uuid(type_, compiler, **kwargs):
    return "CHAR(32)"


class MCPTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/test.db",
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)
        with self.session() as db:
            alice = User(email="alice@test", display_name="Alice")
            bob = User(email="bob@test", display_name="Bob")
            db.add_all([alice, bob])
            db.flush()
            self.alice_id = alice.id
            self.full = self.make_pat(db, alice.id, list(ALL_PAT_PERMISSIONS))
            self.read = self.make_pat(db, alice.id, ["entries:read"])
            self.bob = self.make_pat(db, bob.id, list(ALL_PAT_PERMISSIONS))
            project = Project(name="Shared", created_by=alice.id)
            db.add(project)
            db.flush()
            self.project_id = str(project.id)
            db.add_all(
                [
                    ProjectMember(
                        project_id=project.id,
                        user_id=alice.id,
                        role=ProjectRole.OWNER,
                    ),
                    ProjectMember(
                        project_id=project.id,
                        user_id=bob.id,
                        role=ProjectRole.VIEWER,
                    ),
                ],
            )
            private = Entry(
                title="Private",
                user_id=alice.id,
                source_type=SourceType.UPLOAD,
                status=EntryStatus.READY,
                transcript="a" * 20010,
            )
            shared = Entry(
                title="Shared",
                user_id=alice.id,
                project_id=project.id,
                source_type=SourceType.UPLOAD,
                status=EntryStatus.READY,
                transcript="Meeting notes",
            )
            db.add_all([private, shared])
            db.commit()
            self.private_id, self.shared_id = str(private.id), str(shared.id)
        mode = patch.object(settings, "auth_mode", AuthMode.OIDC)
        mode.start()
        self.addCleanup(mode.stop)

        @asynccontextmanager
        async def lifespan(app):
            async with app.state.mcp_server.session_manager.run():
                yield

        self.app = FastAPI(lifespan=lifespan)
        for router, prefix in [
            (auth.router, "auth"),
            (entries.router, "entries"),
            (projects.router, "projects"),
            (prompt_templates.router, "prompt-templates"),
        ]:
            self.app.include_router(router, prefix=f"/api/{prefix}")

        def test_db():
            with self.session() as db:
                yield db

        self.app.dependency_overrides[get_db] = test_db
        install_mcp(
            self.app,
            Settings(_env_file=None, mcp_allowed_hosts="testserver,127.0.0.1:*"),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    @staticmethod
    def make_pat(db, user_id, scopes):
        _, raw = PATService(db).create(
            user_id=user_id,
            name="MCP test",
            permissions=scopes,
            expires_at=None,
        )
        return raw

    def rpc(self, method, params=None, token=None, headers=None):
        request_headers = {
            "Authorization": f"Bearer {token or self.full}",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        }
        request_headers.update(headers or {})
        return self.client.post(
            "/mcp",
            headers=request_headers,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        )

    def call(self, name, arguments=None, token=None):
        response = self.rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            token,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]

    def data(self, name, arguments=None, token=None):
        result = self.call(name, arguments, token)
        self.assertFalse(result.get("isError"), result)
        return result["structuredContent"]

    def test_discovery_and_protocol_validation(self):
        response = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        self.assertEqual(response.json()["result"]["protocolVersion"], "2025-11-25")
        tools = self.rpc("tools/list").json()["result"]["tools"]
        self.assertEqual(len(tools), 15)
        self.assertTrue(
            all("inputSchema" in tool and "outputSchema" in tool for tool in tools),
        )
        delete = next(t for t in tools if t["name"] == "delete_entry")
        self.assertTrue(delete["annotations"]["destructiveHint"])
        self.assertEqual(
            len(
                self.rpc("resources/templates/list").json()["result"][
                    "resourceTemplates"
                ],
            ),
            6,
        )
        self.assertEqual(
            self.rpc(
                "tools/list",
                headers={"MCP-Protocol-Version": "2099-01-01"},
            ).status_code,
            400,
        )
        self.assertIn("error", self.rpc("unknown/method").json())

    def test_pat_required_in_every_auth_mode_and_transport_method(self):
        for mode in AuthMode:
            with patch.object(settings, "auth_mode", mode):
                for credential in (
                    "",
                    "Bearer legacy",
                    "Bearer vvpat_bad",
                    "Bearer vvpat_" + "x" * 40,
                ):
                    for method in ("GET", "POST", "DELETE"):
                        with self.subTest(
                            mode=mode,
                            credential=credential,
                            method=method,
                        ):
                            response = self.client.request(
                                method,
                                "/mcp",
                                headers={
                                    "Authorization": credential,
                                    "Cookie": "session=fake",
                                },
                            )
                            self.assertEqual(response.status_code, 401)
                            self.assertEqual(
                                response.headers["www-authenticate"],
                                "Bearer",
                            )
        response = self.client.post(
            "/mcp",
            headers=[
                ("Authorization", f"Bearer {self.full}"),
                ("Authorization", f"Bearer {self.bob}"),
            ],
        )
        self.assertEqual(response.status_code, 401)

    def test_expired_revoked_and_inactive_credentials(self):
        for field in ("expires_at", "revoked_at", "inactive"):
            with self.subTest(field=field), self.session() as db:
                token = self.make_pat(db, self.alice_id, ["entries:read"])
                pat = PATService(db).validate(token).token
                if field == "inactive":
                    db.get(User, self.alice_id).is_active = False
                else:
                    setattr(pat, field, utcnow() - timedelta(seconds=1))
                db.commit()
                self.assertEqual(self.rpc("tools/list", token=token).status_code, 401)

    def test_revocation_after_discovery(self):
        self.assertEqual(self.rpc("tools/list").status_code, 200)
        with self.session() as db:
            pat = PATService(db).validate(self.full).token
            PATService(db).revoke(pat.id)
        self.assertEqual(
            self.rpc("tools/call", {"name": "list_entries"}).status_code,
            401,
        )

    def test_origin_and_host_protection(self):
        self.assertEqual(
            self.rpc("tools/list", headers={"Origin": "https://evil.test"}).status_code,
            403,
        )
        self.assertEqual(
            self.rpc("tools/list", headers={"Host": "evil.test"}).status_code,
            421,
        )
        self.assertEqual(
            self.rpc(
                "tools/list",
                headers={"Origin": "http://localhost:3000"},
            ).status_code,
            200,
        )

    def test_create_read_update_archive_and_delete_through_rest(self):
        created = self.data(
            "create_entry_from_transcript",
            {"data": {"title": "Created via MCP", "transcript": "Test transcript"}},
        )
        entry_id = created["id"]
        headers = {"Authorization": f"Bearer {self.full}"}
        self.assertEqual(
            self.client.get(f"/api/entries/{entry_id}", headers=headers).json()[
                "transcript"
            ],
            "Test transcript",
        )
        self.assertEqual(
            self.data(
                "update_entry_metadata",
                {"entry_id": entry_id, "data": {"title": "Renamed"}},
            )["title"],
            "Renamed",
        )
        self.assertEqual(
            self.data(
                "update_entry_status",
                {"entry_id": entry_id, "status": "COMPLETE"},
            )["status"],
            "COMPLETE",
        )
        denied = self.call(
            "set_entry_archived",
            {"entry_id": entry_id, "archived": True},
        )
        self.assertTrue(denied["isError"])
        self.data("update_entry_status", {"entry_id": entry_id, "status": "READY"})
        self.assertTrue(
            self.data("set_entry_archived", {"entry_id": entry_id, "archived": True})[
                "archived"
            ],
        )
        self.assertEqual(
            self.data(
                "move_entry_to_project",
                {"entry_id": entry_id, "project_id": self.project_id},
            )["project_id"],
            self.project_id,
        )
        self.data("delete_entry", {"entry_id": entry_id})
        self.assertEqual(
            self.client.get(f"/api/entries/{entry_id}", headers=headers).status_code,
            404,
        )

    def test_url_project_templates_and_filters(self):
        result = self.data(
            "create_entry_from_url",
            {"title": "URL", "source_url": "https://example.org/test.mp3"},
        )
        self.assertEqual(result["status"], "NEW")
        self.assertEqual(
            self.data("get_entry", {"entry_id": result["id"]})["title"],
            "URL",
        )
        self.assertEqual(len(self.data("list_projects")["projects"]), 1)
        self.assertEqual(
            self.data("get_project", {"project_id": self.project_id})["name"],
            "Shared",
        )
        self.assertEqual(self.data("list_prompt_templates"), {"templates": []})
        listing = self.data(
            "list_entries",
            {
                "page": 1,
                "per_page": 1,
                "search": "Private",
                "owner": "me",
                "project_id": "none",
            },
        )
        self.assertEqual(listing["total"], 1)
        self.assertNotIn("transcript", listing["entries"][0])
        for value in (0, 101):
            self.assertTrue(self.call("list_entries", {"per_page": value})["isError"])
        self.assertTrue(
            self.call("get_entry", {"entry_id": "../../auth/pats"})["isError"],
        )

    def test_scope_and_project_access_are_both_enforced(self):
        for name, arguments in [
            (
                "create_entry_from_transcript",
                {"data": {"title": "no", "transcript": "no"}},
            ),
            ("generate_entry_summary", {"entry_id": self.private_id}),
            ("list_projects", {}),
            ("list_prompt_templates", {}),
        ]:
            result = self.call(name, arguments, self.read)
            self.assertTrue(result["isError"])
            self.assertIn("403", result["content"][0]["text"])
        self.assertEqual(
            self.data("get_entry", {"entry_id": self.shared_id}, self.bob)["title"],
            "Shared",
        )
        for name in ("generate_entry_summary", "delete_entry"):
            result = self.call(name, {"entry_id": self.shared_id}, self.bob)
            self.assertTrue(result["isError"])
            self.assertIn("403", result["content"][0]["text"])
        self.assertIn(
            "404",
            self.call("get_entry", {"entry_id": self.private_id}, self.bob)["content"][
                0
            ]["text"],
        )
        resources = self.rpc(
            "resources/read",
            {"uri": f"voicevault://entries/{self.private_id}/transcript"},
            self.bob,
        ).json()
        self.assertIn("error", resources)
        self.assertNotIn("a" * 100, json.dumps(resources))

    def test_resources_and_bounded_text(self):
        uri = f"voicevault://entries/{self.private_id}/transcript"
        first = self.rpc("resources/read", {"uri": uri}).json()["result"]
        page = json.loads(first["contents"][0]["text"])
        self.assertEqual(len(page["text"]), 20000)
        second = self.rpc("resources/read", {"uri": page["next_uri"]}).json()["result"]
        self.assertEqual(json.loads(second["contents"][0]["text"])["text"], "a" * 10)
        self.assertEqual(
            self.data(
                "read_entry_text",
                {"entry_id": self.private_id, "offset": 20000},
            )["text"],
            "a" * 10,
        )
        for uri in (
            f"voicevault://entries/{self.private_id}",
            f"voicevault://entries/{self.private_id}/summary",
            f"voicevault://projects/{self.project_id}",
        ):
            self.assertIn("result", self.rpc("resources/read", {"uri": uri}).json())
        with self.session() as db:
            self.assertIsNone(db.get(Entry, UUID(self.private_id)).summary)

    def test_chat_and_summary_preserve_rest_behavior(self):
        with patch("app.api.routes.entries.ChatService") as service:
            service.return_value.chat_with_entry = AsyncMock(return_value="Answer")
            service.return_value.generate_summary = AsyncMock(
                return_value="Saved summary",
            )
            self.assertEqual(
                self.data(
                    "chat_with_entry",
                    {"entry_id": self.shared_id, "data": {"message": "Explain"}},
                    self.bob,
                )["message"],
                "Answer",
            )
            self.assertEqual(
                self.data("generate_entry_summary", {"entry_id": self.private_id})[
                    "summary"
                ],
                "Saved summary",
            )
            self.assertEqual(
                self.data(
                    "read_entry_text",
                    {"entry_id": self.private_id, "field": "summary"},
                )["text"],
                "Saved summary",
            )
            service.return_value.generate_summary.side_effect = RuntimeError(
                "sensitive-provider-details",
            )
            error = self.call("generate_entry_summary", {"entry_id": self.private_id})
            self.assertTrue(error["isError"])
            self.assertNotIn("sensitive-provider-details", json.dumps(error))

    def test_search_preserves_literal_json_strings(self):
        for search in ("null", "[]", "{}", "true", '"quoted"'):
            with self.subTest(search=search):
                created = self.data(
                    "create_entry_from_transcript",
                    {"data": {"title": search, "transcript": "Fixture"}},
                )
                result = self.data("list_entries", {"search": search})
                self.assertEqual(
                    [entry["id"] for entry in result["entries"]],
                    [created["id"]],
                )
        self.assertEqual(self.data("list_entries", {"search": None})["total"], 7)
        self.assertEqual(self.data("list_entries")["total"], 7)

    def test_validation_errors_do_not_echo_inputs(self):
        secret = "PRIVATE_TRANSCRIPT_MARKER"
        for name, arguments, field in (
            (
                "create_entry_from_transcript",
                {"data": {"transcript": secret}},
                "data.title",
            ),
            (
                "update_entry_metadata",
                {"entry_id": self.private_id, "data": {"speakers": secret * 100}},
                "data.speakers",
            ),
            ("get_entry", {"entry_id": secret}, "entry_id"),
            (
                "chat_with_entry",
                {
                    "entry_id": self.private_id,
                    "data": {
                        "message": secret,
                        "conversation_history": [{"content": secret}],
                    },
                },
                "data.conversation_history.0.role",
            ),
        ):
            with self.subTest(name=name):
                result = self.call(name, arguments)
                self.assertTrue(result["isError"])
                self.assertNotIn(secret, json.dumps(result))
                self.assertIn(field, result["content"][0]["text"])
        result = self.rpc(
            "resources/read",
            {"uri": f"voicevault://entries/{secret}"},
        ).json()
        self.assertIn("error", result)
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("entry_id", result["error"]["message"])

    def test_stalled_provider_is_cancelled_by_operation_deadline(self):
        from groq import AsyncGroq

        cancelled = []

        async def stalled(request):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)
            raise AssertionError("Provider should have been cancelled")

        def client(**kwargs):
            return AsyncGroq(
                **kwargs,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(stalled)),
            )

        with (
            patch.object(settings, "llm_provider", "groq"),
            patch.object(settings, "groq_api_key", "test-key"),
            patch("app.services.chat_service.AsyncGroq", side_effect=client),
            patch("app.mcp.adapter.OPERATION_TIMEOUT_SECONDS", 0.1),
        ):
            for name, arguments in (
                (
                    "chat_with_entry",
                    {"entry_id": self.private_id, "data": {"message": "Explain"}},
                ),
                ("generate_entry_summary", {"entry_id": self.private_id}),
            ):
                with self.subTest(name=name):
                    start = time.monotonic()
                    result = self.call(name, arguments)
                    self.assertLess(time.monotonic() - start, 2)
                    self.assertTrue(result["isError"])
                    self.assertIn("503", result["content"][0]["text"])
        self.assertEqual(len(cancelled), 2)
        with self.session() as db:
            self.assertIsNone(db.get(Entry, UUID(self.private_id)).summary)
        self.assertEqual(self.data("list_entries")["total"], 2)

    def test_independent_sdk_client_over_tcp_and_concurrent_users(self):
        # A separate server instance: SDK session managers are single-use.
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        network_app = FastAPI()
        network_app.router.routes = [
            r for r in self.app.router.routes if r.path != "/mcp"
        ]
        # REST routes retain their original dependency override provider.
        server_mcp = install_mcp(
            network_app,
            Settings(_env_file=None, mcp_allowed_hosts="127.0.0.1:*"),
        )

        @asynccontextmanager
        async def lifespan(app):
            async with server_mcp.session_manager.run():
                yield

        network_app.router.lifespan_context = lifespan
        server = uvicorn.Server(
            uvicorn.Config(network_app, log_level="error", ws="none"),
        )
        thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [sock]},
            daemon=True,
        )
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while (
                not server.started and thread.is_alive() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertTrue(server.started)

            async def run(token, expected):
                async with (
                    httpx.AsyncClient(
                        headers={"Authorization": f"Bearer {token}"},
                    ) as http,
                    streamable_http_client(
                        f"http://127.0.0.1:{port}/mcp",
                        http_client=http,
                    ) as (read, write, _),
                    ClientSession(read, write) as client,
                ):
                    await client.initialize()
                    self.assertEqual(len((await client.list_tools()).tools), 15)
                    for _ in range(3):
                        result = await client.call_tool("list_entries", {})
                        self.assertEqual(result.structuredContent["total"], expected)
                    resource = await client.read_resource(
                        f"voicevault://entries/{self.shared_id}/transcript",
                    )
                    self.assertIn("Meeting notes", resource.contents[0].text)

            async def concurrent():
                await asyncio.gather(run(self.full, 2), run(self.bob, 1))

            asyncio.run(concurrent())
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            self.assertFalse(thread.is_alive())
