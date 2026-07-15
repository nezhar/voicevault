import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.user_service import SYSTEM_USER_EMAIL, UserService


class SystemUserTests(TestCase):
    def test_returns_existing_system_user(self):
        db = MagicMock()
        existing = SimpleNamespace(id=uuid4(), is_system=True)
        db.query.return_value.filter.return_value.first.return_value = existing

        result = UserService(db).get_or_create_system_user()

        self.assertIs(result, existing)
        db.add.assert_not_called()

    def test_creates_system_user_when_missing(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        UserService(db).get_or_create_system_user()

        db.add.assert_called_once()
        db.commit.assert_called_once()
        created = db.add.call_args.args[0]
        self.assertTrue(created.is_system)
        self.assertEqual(created.email, SYSTEM_USER_EMAIL)

    def test_concurrent_create_falls_back_to_existing_row(self):
        from sqlalchemy.exc import IntegrityError

        db = MagicMock()
        winner = SimpleNamespace(id=uuid4(), is_system=True)
        # first lookup misses, the post-conflict lookup finds the other
        # replica's row
        db.query.return_value.filter.return_value.first.side_effect = [None, winner]
        db.commit.side_effect = IntegrityError("INSERT", {}, Exception("dup email"))

        result = UserService(db).get_or_create_system_user()

        self.assertIs(result, winner)
        db.rollback.assert_called_once()


class ProvisionOidcUserTests(TestCase):
    def test_updates_existing_user_on_login(self):
        db = MagicMock()
        existing = SimpleNamespace(
            id=uuid4(),
            issuer="https://idp.test",
            subject="abc",
            email="old@test",
            display_name="Old",
            last_login_at=None,
        )
        db.query.return_value.filter.return_value.first.return_value = existing

        result = UserService(db).provision_oidc_user(
            issuer="https://idp.test",
            subject="abc",
            email="New@Test",
            display_name="New Name",
        )

        self.assertIs(result, existing)
        self.assertEqual(existing.email, "new@test")
        self.assertEqual(existing.display_name, "New Name")
        self.assertIsNotNone(existing.last_login_at)
        db.commit.assert_called_once()

    def test_creates_user_on_first_login_with_email_fallback_name(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        UserService(db).provision_oidc_user(
            issuer="https://idp.test",
            subject="abc",
            email="User@Test",
            display_name=None,
        )

        created = db.add.call_args.args[0]
        self.assertEqual(created.email, "user@test")
        self.assertEqual(created.display_name, "user@test")
        self.assertEqual(created.subject, "abc")


class ClaimLegacyEntriesTests(TestCase):
    def test_claims_orphans_and_system_user_entries(self):
        db = MagicMock()
        owner = SimpleNamespace(id=uuid4(), email="admin@corp", is_system=False)
        system_user = SimpleNamespace(id=uuid4(), is_system=True)
        service = UserService(db)
        service.get_or_create_system_user = MagicMock(return_value=system_user)
        db.query.return_value.filter.return_value.update.return_value = 3

        claimed = service.claim_legacy_entries(owner)

        self.assertEqual(claimed, 3)
        db.commit.assert_called_once()
