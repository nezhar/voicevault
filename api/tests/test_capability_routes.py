"""Capabilities and group sharing against the real app, routes and SQLite."""

import os
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LLM_BASE_URL", "http://llm.invalid/v1")
os.environ.setdefault("LLM_MODEL", "test")

from fastapi.testclient import TestClient
from sqlite_support import sqlite_sessionmaker

from app.core import auth as auth_module
from app.core.config import AuthMode
from app.db.database import get_db
from app.main import app
from app.models.capability_grant import CapabilityGrant
from app.models.entry import Entry, EntryStatus, SourceType
from app.models.group import Group, GroupMember, MembershipSource
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User
from app.services.group_service import GroupService
from app.services.pat_service import PATService
from app.services.permission_service import PermissionService
from app.services.session_service import SESSION_COOKIE_NAME, SessionService


class CapabilityRouteTestCase(TestCase):
    def setUp(self):
        self.Session = sqlite_sessionmaker(self)
        for name, value in (
            ("auth_mode", AuthMode.OIDC),
            ("admin_emails", "admin@test"),
        ):
            patcher = patch.object(auth_module.settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(app.dependency_overrides.pop, get_db, None)

        with self.Session() as db:
            self.admin = self.add_user(db, "admin@test")
            self.alice = self.add_user(db, "alice@test")
            self.bob = self.add_user(db, "bob@test")
            PermissionService(db).seed_defaults()
            self.everyone = db.query(Group).filter(Group.is_builtin.is_(True)).one().id
            project = Project(name="Team", created_by=self.alice)
            db.add(project)
            db.flush()
            self.project = project.id
            db.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=self.alice,
                    role=ProjectRole.OWNER,
                ),
            )
            self.alice_entry = self.add_entry(db, self.alice, None, "Alice private")
            self.team_entry = self.add_entry(db, self.alice, project.id, "Team entry")
            db.commit()

    @staticmethod
    def add_user(db, email):
        user = User(
            email=email,
            display_name=email.split("@")[0],
            issuer="i",
            subject=email,
        )
        db.add(user)
        db.flush()
        return user.id

    @staticmethod
    def add_entry(db, user_id, project_id, title):
        entry = Entry(
            title=title,
            source_type=SourceType.UPLOAD,
            status=EntryStatus.READY,
            transcript="hello",
            user_id=user_id,
            project_id=project_id,
        )
        db.add(entry)
        db.flush()
        return entry.id

    def client_for(self, user_id) -> TestClient:
        with self.Session() as db:
            _, token = SessionService(db).create_session(user_id)
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE_NAME, token)
        return client

    def pat_for(self, user_id, permissions, project_ids=None) -> TestClient:
        with self.Session() as db:
            _, raw = PATService(db).create(
                user_id=user_id,
                name="t",
                permissions=permissions,
                expires_at=None,
                project_ids=project_ids,
            )
        return TestClient(app, headers={"Authorization": f"Bearer {raw}"})

    def set_group_grants(self, group_id, caps):
        with self.Session() as db:
            db.query(CapabilityGrant).filter_by(group_id=group_id).delete()
            for cap in caps:
                db.add(CapabilityGrant(group_id=group_id, capability=cap))
            db.commit()

    def grant_user(self, user_id, cap, project_id=None):
        with self.Session() as db:
            db.add(
                CapabilityGrant(user_id=user_id, capability=cap, project_id=project_id),
            )
            db.commit()


class EntryCapabilityTests(CapabilityRouteTestCase):
    def test_defaults_keep_everything_working(self):
        client = self.client_for(self.alice)
        self.assertEqual(
            client.get(f"/api/entries/{self.alice_entry}").status_code,
            200,
        )
        me = client.get("/api/auth/me").json()
        self.assertIn("entries.chat", me["capabilities"])
        self.assertNotIn("admin.view", me["capabilities"])

    def test_missing_capability_is_403_with_a_clear_message(self):
        self.set_group_grants(self.everyone, ["entries.view"])
        client = self.client_for(self.alice)
        response = client.get(f"/api/entries/{self.alice_entry}/subtitles")
        self.assertEqual(response.status_code, 403)
        self.assertIn("entries.export", response.json()["detail"])
        self.assertIn("globally", response.json()["detail"])

    def test_project_grant_adds_only_in_that_project(self):
        self.set_group_grants(self.everyone, ["entries.view"])
        self.grant_user(self.alice, "entries.edit", self.project)
        client = self.client_for(self.alice)
        archive = {"archived": True}
        self.assertEqual(
            client.put(
                f"/api/entries/{self.team_entry}/archive",
                json=archive,
            ).status_code,
            200,
        )
        response = client.put(f"/api/entries/{self.alice_entry}/archive", json=archive)
        self.assertEqual(response.status_code, 403)

    def test_list_is_filtered_to_where_view_holds(self):
        self.set_group_grants(self.everyone, [])
        self.grant_user(self.alice, "entries.view", self.project)
        listing = self.client_for(self.alice).get("/api/entries/").json()
        self.assertEqual([e["title"] for e in listing["entries"]], ["Team entry"])

    def test_capability_never_makes_content_visible(self):
        self.grant_user(self.bob, "entries.view", self.project)
        client = self.client_for(self.bob)
        self.assertEqual(client.get(f"/api/entries/{self.team_entry}").status_code, 404)
        self.assertEqual(client.get("/api/entries/").json()["total"], 0)

    def test_projects_create_can_be_withdrawn(self):
        self.set_group_grants(self.everyone, ["entries.view"])
        response = self.client_for(self.bob).post("/api/projects/", json={"name": "X"})
        self.assertEqual(response.status_code, 403)


class TokenCapabilityTests(CapabilityRouteTestCase):
    def test_token_cannot_exceed_owner_after_grant_is_revoked(self):
        client = self.pat_for(self.alice, ["entries.view", "entries.chat"])
        self.assertEqual(
            client.get(f"/api/entries/{self.alice_entry}").status_code,
            200,
        )
        self.set_group_grants(self.everyone, ["entries.chat"])
        self.assertEqual(
            client.get(f"/api/entries/{self.alice_entry}").status_code,
            403,
        )

    def test_project_limited_token(self):
        client = self.pat_for(self.alice, ["entries.view"], [self.project])
        self.assertEqual(client.get(f"/api/entries/{self.team_entry}").status_code, 200)
        self.assertEqual(
            client.get(f"/api/entries/{self.alice_entry}").status_code,
            403,
        )
        titles = [e["title"] for e in client.get("/api/entries/").json()["entries"]]
        self.assertEqual(titles, ["Team entry"])

    def test_create_pat_refuses_capabilities_the_owner_lacks(self):
        client = self.client_for(self.alice)
        response = client.post(
            "/api/auth/pats",
            json={"name": "x", "permissions": ["admin.manage"]},
        )
        self.assertEqual(response.status_code, 403)
        response = client.post(
            "/api/auth/pats",
            json={"name": "x", "permissions": ["entries:read"]},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["permissions"],
            ["entries.chat", "entries.export", "entries.view", "mcp.connect"],
        )

    def test_create_pat_needs_tokens_create(self):
        self.set_group_grants(self.everyone, ["entries.view"])
        response = self.client_for(self.alice).post(
            "/api/auth/pats",
            json={"name": "x", "permissions": ["entries.view"]},
        )
        self.assertEqual(response.status_code, 403)

    def test_create_pat_refuses_projects_the_owner_cannot_reach(self):
        response = self.client_for(self.bob).post(
            "/api/auth/pats",
            json={
                "name": "x",
                "permissions": ["entries.view"],
                "project_ids": [str(self.project)],
            },
        )
        self.assertEqual(response.status_code, 404)


class GroupProjectTests(CapabilityRouteTestCase):
    def make_group(self, name="Sales", members=(), idp=None):
        with self.Session() as db:
            group = Group(name=name, idp_group=idp)
            db.add(group)
            db.flush()
            for user_id in members:
                db.add(
                    GroupMember(
                        group_id=group.id,
                        user_id=user_id,
                        source=MembershipSource.MANUAL,
                    ),
                )
            db.commit()
            return group.id

    def test_sharing_with_a_group_gives_its_members_access(self):
        sales = self.make_group(members=[self.bob])
        owner = self.client_for(self.alice)
        response = owner.post(
            f"/api/projects/{self.project}/groups",
            json={"group_id": str(sales), "role": "editor"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["member_count"], 1)

        bob = self.client_for(self.bob)
        self.assertEqual(bob.get(f"/api/entries/{self.team_entry}").status_code, 200)
        projects = bob.get("/api/projects/").json()
        self.assertEqual(
            [(p["name"], p["my_role"]) for p in projects],
            [("Team", "editor")],
        )
        detail = bob.get(f"/api/projects/{self.project}").json()
        self.assertEqual(detail["my_access_via"], ["Sales"])
        self.assertEqual(detail["groups"][0]["name"], "Sales")

    def test_groups_cannot_be_owners(self):
        sales = self.make_group()
        response = self.client_for(self.alice).post(
            f"/api/projects/{self.project}/groups",
            json={"group_id": str(sales), "role": "owner"},
        )
        self.assertEqual(response.status_code, 422)

    def test_highest_role_wins(self):
        sales = self.make_group(members=[self.bob])
        with self.Session() as db:
            db.add(
                ProjectMember(
                    project_id=self.project,
                    user_id=self.bob,
                    role=ProjectRole.VIEWER,
                ),
            )
            db.commit()
        owner = self.client_for(self.alice)
        owner.post(
            f"/api/projects/{self.project}/groups",
            json={"group_id": str(sales), "role": "editor"},
        )
        response = self.client_for(self.bob).put(
            f"/api/entries/{self.team_entry}/archive",
            json={"archived": True},
        )
        self.assertEqual(response.status_code, 200)

    def test_sharing_with_everyone_reaches_every_user(self):
        self.client_for(self.alice).post(
            f"/api/projects/{self.project}/groups",
            json={"group_id": str(self.everyone), "role": "viewer"},
        )
        bob = self.client_for(self.bob)
        self.assertEqual(bob.get(f"/api/entries/{self.team_entry}").status_code, 200)
        self.assertEqual(
            bob.put(
                f"/api/entries/{self.team_entry}/archive",
                json={"archived": True},
            ).status_code,
            403,
        )

    def test_group_only_access_cannot_leave_or_request(self):
        sales = self.make_group(members=[self.bob])
        self.client_for(self.alice).post(
            f"/api/projects/{self.project}/groups",
            json={"group_id": str(sales), "role": "viewer"},
        )
        bob = self.client_for(self.bob)
        response = bob.delete(f"/api/projects/{self.project}/members/{self.bob}")
        self.assertEqual(response.status_code, 409)
        self.assertIn("Sales", response.json()["detail"])
        response = bob.post(f"/api/projects/{self.project}/access-requests", json={})
        self.assertEqual(response.status_code, 409)
        self.assertIn("Sales", response.json()["detail"])

    def test_removing_the_share_ends_access(self):
        sales = self.make_group(members=[self.bob])
        owner = self.client_for(self.alice)
        owner.post(
            f"/api/projects/{self.project}/groups",
            json={"group_id": str(sales), "role": "viewer"},
        )
        self.assertEqual(
            owner.delete(f"/api/projects/{self.project}/groups/{sales}").status_code,
            200,
        )
        bob = self.client_for(self.bob)
        self.assertEqual(bob.get(f"/api/entries/{self.team_entry}").status_code, 404)

    def test_managing_shares_needs_projects_manage(self):
        sales = self.make_group()
        self.set_group_grants(self.everyone, ["entries.view"])
        response = self.client_for(self.alice).post(
            f"/api/projects/{self.project}/groups",
            json={"group_id": str(sales), "role": "viewer"},
        )
        self.assertEqual(response.status_code, 403)

    def test_idp_sync_adds_and_removes_but_keeps_manual(self):
        sales = self.make_group(idp="sales")
        manual = self.make_group(name="Manual", members=[self.bob])
        with self.Session() as db:
            bob = db.get(User, self.bob)
            service = GroupService(db)
            service.sync_idp_memberships(bob, ["Sales", "Unknown"])
            self.assertEqual(
                service.group_names_for(bob.id),
                ["Everyone", "Manual", "Sales"],
            )
            service.sync_idp_memberships(bob, None)
            self.assertEqual(service.group_names_for(bob.id), ["Everyone", "Manual"])
            self.assertIsNotNone(sales)
            self.assertIsNotNone(manual)


class AdminApiTests(CapabilityRouteTestCase):
    def test_non_admins_get_404(self):
        client = self.client_for(self.alice)
        for method, path in (
            ("get", "/api/admin/groups"),
            ("get", f"/api/admin/grants?user_id={self.alice}"),
            ("get", f"/api/admin/users/{self.alice}/effective"),
        ):
            self.assertEqual(getattr(client, method)(path).status_code, 404, path)

    def test_admin_manages_groups_members_and_grants(self):
        admin = self.client_for(self.admin)
        groups = admin.get("/api/admin/groups").json()
        self.assertEqual(groups[0]["name"], "Everyone")
        self.assertIsNone(groups[0]["member_count"])

        created = admin.post(
            "/api/admin/groups",
            json={"name": "Sales", "idp_group": " Sales-Team "},
        )
        self.assertEqual(created.status_code, 201, created.text)
        group_id = created.json()["id"]
        self.assertEqual(created.json()["idp_group"], "sales-team")

        added = admin.post(
            f"/api/admin/groups/{group_id}/members",
            json={"email": "bob@test"},
        )
        self.assertEqual(added.json()["members"][0]["source"], "manual")

        grants = admin.put(
            f"/api/admin/grants?group_id={group_id}",
            json={
                "grants": [
                    {"capability": "templates.manage"},
                    {"capability": "entries.chat", "project_id": str(self.project)},
                ],
            },
        )
        self.assertEqual(grants.status_code, 200, grants.text)
        self.assertIn("Team", {g["project_name"] for g in grants.json()})

        effective = admin.get(f"/api/admin/users/{self.bob}/effective").json()
        self.assertIn("templates.manage", effective["capabilities"])
        self.assertIn("Sales", effective["groups"])
        sources = {(g["capability"], g["source"]) for g in effective["grants"]}
        self.assertIn(("templates.manage", "Sales"), sources)
        self.assertIn(("entries.view", "Everyone"), sources)

    def test_everyone_is_protected(self):
        admin = self.client_for(self.admin)
        self.assertEqual(
            admin.delete(f"/api/admin/groups/{self.everyone}").status_code,
            409,
        )
        self.assertEqual(
            admin.put(
                f"/api/admin/groups/{self.everyone}",
                json={"name": "All"},
            ).status_code,
            409,
        )

    def test_global_only_capability_refused_per_project(self):
        response = self.client_for(self.admin).put(
            f"/api/admin/grants?user_id={self.alice}",
            json={
                "grants": [
                    {"capability": "tokens.create", "project_id": str(self.project)},
                ],
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_admin_view_grant_opens_reads_but_not_writes(self):
        self.grant_user(self.alice, "admin.view")
        client = self.client_for(self.alice)
        self.assertEqual(client.get("/api/admin/groups").status_code, 200)
        self.assertEqual(
            client.post("/api/admin/groups", json={"name": "X"}).status_code,
            404,
        )

    def test_pat_is_refused_on_admin_management(self):
        client = self.pat_for(self.admin, ["admin.view", "admin.manage"])
        self.assertEqual(client.get("/api/admin/groups").status_code, 403)
        self.assertEqual(client.get("/api/admin/stats").status_code, 200)

    def test_admin_project_search(self):
        found = self.client_for(self.admin).get("/api/admin/projects?search=tea").json()
        self.assertEqual([p["name"] for p in found], ["Team"])
        self.assertEqual(
            self.client_for(self.alice).get("/api/admin/projects").status_code,
            404,
        )

    def test_catalog_lists_routes_and_tools(self):
        catalog = self.client_for(self.bob).get("/api/capabilities").json()
        chat = next(item for item in catalog if item["name"] == "entries.chat")
        self.assertTrue(chat["project_scoped"])
        self.assertIn("chat_with_entry", chat["tools"])
        self.assertIn("POST /api/entries/{entry_id}/chat", chat["routes"])
