import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlite_support import sqlite_sessionmaker

from app.core.capabilities import ALL_CAPABILITIES, DEFAULT_EVERYONE, Capability as C
from app.models.capability_grant import CapabilityGrant
from app.models.group import Group, GroupMember, MembershipSource
from app.models.personal_access_token import PersonalAccessToken
from app.models.project import Project
from app.models.user import User
from app.services.permission_service import (
    Effective,
    GrantError,
    GrantSpec,
    PermissionService,
)


class PermissionServiceTests(TestCase):
    def setUp(self):
        self.Session = sqlite_sessionmaker(self)
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.alice = User(email="alice@test", display_name="Alice")
        self.bob = User(email="bob@test", display_name="Bob")
        self.db.add_all([self.alice, self.bob])
        self.db.flush()
        self.p1 = Project(name="P1", created_by=self.alice.id)
        self.p2 = Project(name="P2", created_by=self.alice.id)
        self.db.add_all([self.p1, self.p2])
        self.db.commit()
        self.service = PermissionService(self.db)
        admin = patch("app.core.auth.is_admin_user", return_value=False)
        admin.start()
        self.addCleanup(admin.stop)

    def grant(self, cap, *, user=None, group=None, project=None):
        self.db.add(
            CapabilityGrant(
                user_id=user.id if user else None,
                group_id=group.id if group else None,
                capability=cap.value,
                project_id=project.id if project else None,
            ),
        )
        self.db.commit()

    def test_before_seeding_everybody_has_the_defaults(self):
        eff = self.service.effective(self.alice)
        self.assertEqual(eff.global_caps, DEFAULT_EVERYONE)

    def test_no_grants_means_nothing(self):
        self.service.everyone()
        self.db.commit()
        eff = self.service.effective(self.alice)
        self.assertFalse(eff.has(C.ENTRIES_VIEW))
        self.assertFalse(eff.has(C.ENTRIES_VIEW, self.p1.id))

    def test_seed_gives_everyone_the_defaults_once(self):
        self.assertTrue(self.service.seed_defaults())
        self.assertFalse(self.service.seed_defaults())
        eff = self.service.effective(self.bob)
        self.assertEqual(eff.global_caps, DEFAULT_EVERYONE)
        everyone = self.db.query(Group).filter(Group.is_builtin.is_(True)).one()
        self.assertEqual(
            self.db.query(CapabilityGrant).filter_by(group_id=everyone.id).count(),
            len(DEFAULT_EVERYONE),
        )

    def test_union_of_user_group_and_everyone(self):
        everyone = self.service.everyone()
        team = Group(name="Team")
        self.db.add(team)
        self.db.flush()
        self.db.add(
            GroupMember(
                group_id=team.id,
                user_id=self.alice.id,
                source=MembershipSource.MANUAL,
            ),
        )
        self.db.commit()
        self.grant(C.ENTRIES_VIEW, group=everyone)
        self.grant(C.ENTRIES_CHAT, group=team)
        self.grant(C.TOKENS_CREATE, user=self.alice)
        eff = self.service.effective(self.alice)
        self.assertEqual(
            eff.global_caps,
            {C.ENTRIES_VIEW, C.ENTRIES_CHAT, C.TOKENS_CREATE},
        )
        self.assertEqual(self.service.effective(self.bob).global_caps, {C.ENTRIES_VIEW})

    def test_project_grant_only_adds_in_that_project(self):
        self.service.everyone()
        self.db.commit()
        self.grant(C.ENTRIES_CHAT, user=self.alice, project=self.p1)
        eff = self.service.effective(self.alice)
        self.assertTrue(eff.has(C.ENTRIES_CHAT, self.p1.id))
        self.assertFalse(eff.has(C.ENTRIES_CHAT, self.p2.id))
        self.assertFalse(eff.has(C.ENTRIES_CHAT))  # personal entries
        self.assertEqual(eff.projects_with(C.ENTRIES_CHAT), {self.p1.id})
        self.assertTrue(eff.anywhere(C.ENTRIES_CHAT))

    def test_global_only_capability_ignores_project_grants(self):
        self.service.everyone()
        self.db.commit()
        self.grant(C.PROJECTS_CREATE, user=self.alice, project=self.p1)
        eff = self.service.effective(self.alice)
        self.assertFalse(eff.has(C.PROJECTS_CREATE))

    def test_admin_has_everything(self):
        with patch("app.core.auth.is_admin_user", return_value=True):
            eff = self.service.effective(self.alice)
        self.assertEqual(eff.global_caps, ALL_CAPABILITIES)

    def test_token_is_cut_to_owner_and_own_capabilities(self):
        self.service.everyone()
        self.db.commit()
        self.grant(C.ENTRIES_VIEW, user=self.alice)
        self.grant(C.ENTRIES_CHAT, user=self.alice, project=self.p1)
        owner = self.service.effective(self.alice)
        pat = SimpleNamespace(
            permissions=["entries.view", "entries.chat", "entries.delete"],
            project_ids=None,
        )
        eff = PermissionService.for_token(owner, pat)
        self.assertTrue(eff.has(C.ENTRIES_VIEW, self.p2.id))
        self.assertTrue(eff.has(C.ENTRIES_CHAT, self.p1.id))
        self.assertFalse(eff.has(C.ENTRIES_DELETE, self.p1.id))  # owner lacks it

    def test_token_project_filter_excludes_other_projects_and_personal(self):
        self.service.everyone()
        self.db.commit()
        self.grant(C.ENTRIES_VIEW, user=self.alice)
        self.grant(C.TOKENS_CREATE, user=self.alice)
        pat = SimpleNamespace(
            permissions=["entries.view", "tokens.create"],
            project_ids=[str(self.p1.id)],
        )
        eff = PermissionService.for_token(self.service.effective(self.alice), pat)
        self.assertTrue(eff.has(C.ENTRIES_VIEW, self.p1.id))
        self.assertFalse(eff.has(C.ENTRIES_VIEW, self.p2.id))
        self.assertFalse(eff.has(C.ENTRIES_VIEW))
        self.assertTrue(eff.has(C.TOKENS_CREATE))  # global-only still holds
        self.assertEqual(eff.projects_with(C.ENTRIES_VIEW), {self.p1.id})
        self.assertFalse(eff.includes_personal(C.ENTRIES_VIEW))

    def test_replace_grants_is_a_full_replacement(self):
        self.service.replace_grants(
            user_id=self.alice.id,
            actor=None,
            grants=[GrantSpec(C.ENTRIES_VIEW), GrantSpec(C.ENTRIES_CHAT, self.p1.id)],
        )
        self.service.replace_grants(
            user_id=self.alice.id,
            actor=None,
            grants=[GrantSpec(C.ENTRIES_CHAT, self.p1.id), GrantSpec(C.ENTRIES_EXPORT)],
        )
        rows = {
            (g.capability, g.project_id)
            for g in self.service.grants_for(user_id=self.alice.id)
        }
        self.assertEqual(rows, {("entries.chat", self.p1.id), ("entries.export", None)})

    def test_replace_grants_refuses_project_for_global_only(self):
        with self.assertRaises(GrantError):
            self.service.replace_grants(
                user_id=self.alice.id,
                actor=None,
                grants=[GrantSpec(C.TOKENS_CREATE, self.p1.id)],
            )

    def test_replace_grants_refuses_unknown_project(self):
        with self.assertRaises(GrantError):
            self.service.replace_grants(
                user_id=self.alice.id,
                actor=None,
                grants=[GrantSpec(C.ENTRIES_VIEW, uuid4())],
            )

    def test_legacy_tokens_are_converted_once(self):
        pat = PersonalAccessToken(
            user_id=self.alice.id,
            name="old",
            token_hash="h" * 64,
            token_prefix="vvpat_xxxxxxxxxx",
            permissions=["entries:read", "projects:read"],
        )
        self.db.add(pat)
        self.db.commit()
        self.assertEqual(self.service.convert_legacy_tokens(), 1)
        self.assertEqual(self.service.convert_legacy_tokens(), 0)
        self.db.refresh(pat)
        self.assertEqual(
            pat.permissions,
            ["entries.chat", "entries.export", "entries.view", "mcp.connect"],
        )

    def test_explain_names_sources(self):
        everyone = self.service.everyone()
        self.db.commit()
        self.grant(C.ENTRIES_VIEW, group=everyone)
        self.grant(C.ENTRIES_CHAT, user=self.alice, project=self.p1)
        rows = self.service.explain(self.alice)
        self.assertIn(
            {"capability": "entries.view", "project_id": None, "source": "Everyone"},
            rows,
        )
        self.assertIn(
            {"capability": "entries.chat", "project_id": self.p1.id, "source": "user"},
            rows,
        )


class EffectiveTests(TestCase):
    def test_projects_with_none_means_everywhere(self):
        eff = Effective(global_caps=frozenset({C.ENTRIES_VIEW}))
        self.assertIsNone(eff.projects_with(C.ENTRIES_VIEW))
        self.assertTrue(eff.includes_personal(C.ENTRIES_VIEW))
