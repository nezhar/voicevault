import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.core import auth as auth_module
from app.core.config import AuthMode
from app.core.timeutils import utcnow
from app.core.capabilities import ALL_CAPABILITIES, Capability
from permission_stubs import stub_permissions
from app.services.pat_service import (
    PAT_MARKER,
    PATService,
    PATValidationFailure,
    PATValidationResult,
    hash_pat,
)


def request(path="/api/entries/", method="GET", authorization=None):
    headers = {"authorization": authorization} if authorization else {}
    return SimpleNamespace(
        cookies={},
        headers=headers,
        method=method,
        url=SimpleNamespace(path=path),
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )


def credentials(token):
    return SimpleNamespace(credentials=token)


class PATServiceTests(TestCase):
    def test_create_returns_secret_once_and_stores_only_hash(self):
        db = MagicMock()
        user_id = uuid4()

        pat, raw = PATService(db).create(
            user_id=user_id,
            name=" CI ",
            permissions=["entries.view"],
            expires_at=None,
        )

        self.assertTrue(raw.startswith(PAT_MARKER))
        self.assertEqual(pat.name, "CI")
        self.assertEqual(pat.token_hash, hash_pat(raw))
        self.assertNotEqual(pat.token_hash, raw)
        self.assertEqual(pat.token_prefix, raw[:16])
        db.add.assert_called_once_with(pat)
        db.commit.assert_called_once()

    def test_list_all_filters_before_counting_and_paginates(self):
        db = MagicMock()
        query = MagicMock()
        rows = [(SimpleNamespace(), SimpleNamespace())]

        db.query.return_value = query
        query.join.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.offset.return_value = query
        query.limit.return_value = query
        query.count.return_value = 101
        query.all.return_value = rows

        result_rows, total = PATService(db).list_all(
            user_id=uuid4(),
            name="deploy",
            status="active",
            skip=25,
            limit=25,
        )

        self.assertEqual(result_rows, rows)
        self.assertEqual(total, 101)
        query.count.assert_called_once_with()
        query.offset.assert_called_once_with(25)
        query.limit.assert_called_once_with(25)

    def test_rejects_expired_token(self):
        raw = PAT_MARKER + "x" * 32
        pat = SimpleNamespace(
            revoked_at=None,
            expires_at=utcnow() - timedelta(seconds=1),
            last_used_at=None,
        )
        user = SimpleNamespace(is_active=True)
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = (
            pat,
            user,
        )

        result = PATService(db).validate(raw)

        self.assertEqual(result.failure, PATValidationFailure.EXPIRED)
        db.commit.assert_not_called()

    def test_valid_token_resolves_without_writing(self):
        raw = PAT_MARKER + "x" * 32
        pat = SimpleNamespace(revoked_at=None, expires_at=None, last_used_at=None)
        user = SimpleNamespace(is_active=True)
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = (
            pat,
            user,
        )

        result = PATService(db).validate(raw)

        self.assertIsNone(result.failure)
        self.assertIs(result.token, pat)
        self.assertIs(result.user, user)
        db.commit.assert_not_called()

    def test_touch_last_used_writes_outside_the_request_session(self):
        db = MagicMock()
        pat = SimpleNamespace(id=uuid4(), last_used_at=None)

        with patch("app.services.pat_service.set_committed_value") as set_value:
            self.assertTrue(PATService(db).touch_last_used(pat))

        connection = db.get_bind.return_value.begin.return_value.__enter__.return_value
        connection.execute.assert_called_once()
        set_value.assert_called_once()
        self.assertEqual(set_value.call_args.args[:2], (pat, "last_used_at"))
        db.commit.assert_not_called()

    def test_touch_last_used_is_throttled(self):
        db = MagicMock()
        pat = SimpleNamespace(id=uuid4(), last_used_at=utcnow() - timedelta(minutes=1))

        self.assertFalse(PATService(db).touch_last_used(pat))

        db.get_bind.assert_not_called()

    def test_touch_last_used_carries_the_interval_into_the_update(self):
        # The in-memory check cannot hold the interval on its own: concurrent
        # requests read the same stale value, so the predicate has to be in SQL.
        db = MagicMock()
        pat = SimpleNamespace(id=uuid4(), last_used_at=None)

        with patch("app.services.pat_service.set_committed_value"):
            PATService(db).touch_last_used(pat)

        connection = db.get_bind.return_value.begin.return_value.__enter__.return_value
        statement = str(connection.execute.call_args.args[0])
        self.assertIn("last_used_at IS NULL", statement)
        self.assertIn("last_used_at <=", statement)

    def test_touch_last_used_yields_to_the_request_that_won_the_race(self):
        db = MagicMock()
        pat = SimpleNamespace(id=uuid4(), last_used_at=None)
        connection = db.get_bind.return_value.begin.return_value.__enter__.return_value
        connection.execute.return_value.rowcount = 0

        with patch("app.services.pat_service.set_committed_value") as set_value:
            self.assertFalse(PATService(db).touch_last_used(pat))

        set_value.assert_not_called()

    def test_revoke_scopes_to_owner_only_when_asked(self):
        db = MagicMock()
        query = db.query.return_value.filter.return_value
        query.filter.return_value.first.return_value = None
        query.first.return_value = SimpleNamespace(revoked_at=None)

        self.assertFalse(PATService(db).revoke(uuid4(), uuid4()))
        self.assertTrue(PATService(db).revoke(uuid4()))

    def _owned(self, db, pat):
        db.query.return_value.filter.return_value.first.return_value = pat

    def test_update_renames_and_changes_expiry_of_an_active_token(self):
        db = MagicMock()
        pat = SimpleNamespace(name="old", expires_at=None, revoked_at=None)
        self._owned(db, pat)
        later = utcnow() + timedelta(days=30)

        result = PATService(db).update(
            uuid4(),
            uuid4(),
            {"name": "new", "expires_at": later},
        )

        self.assertIs(result, pat)
        self.assertEqual(pat.name, "new")
        self.assertEqual(pat.expires_at, later)
        db.commit.assert_called_once()

    def test_update_leaves_omitted_fields_alone_and_clears_expiry_on_explicit_null(
        self,
    ):
        db = MagicMock()
        pat = SimpleNamespace(
            name="keep",
            expires_at=utcnow() + timedelta(days=1),
            revoked_at=None,
        )
        self._owned(db, pat)

        PATService(db).update(uuid4(), uuid4(), {"expires_at": None})

        self.assertEqual(pat.name, "keep")
        self.assertIsNone(pat.expires_at)

    def test_update_is_a_noop_without_changes(self):
        db = MagicMock()
        self._owned(db, SimpleNamespace(name="x", expires_at=None, revoked_at=None))

        PATService(db).update(uuid4(), uuid4(), {})

        db.commit.assert_not_called()

    def test_update_refuses_expired_and_revoked_tokens(self):
        from app.services.pat_service import PATNotEditable

        for pat in (
            SimpleNamespace(
                name="x",
                expires_at=utcnow() - timedelta(seconds=1),
                revoked_at=None,
            ),
            SimpleNamespace(name="x", expires_at=None, revoked_at=utcnow()),
        ):
            with self.subTest(pat=pat):
                db = MagicMock()
                self._owned(db, pat)
                with self.assertRaises(PATNotEditable):
                    PATService(db).update(uuid4(), uuid4(), {"name": "y"})
                db.commit.assert_not_called()

    def test_update_returns_none_for_foreign_or_unknown_tokens(self):
        db = MagicMock()
        self._owned(db, None)

        self.assertIsNone(PATService(db).update(uuid4(), uuid4(), {"name": "y"}))

    def test_rejects_token_for_inactive_user(self):
        raw = PAT_MARKER + "x" * 32
        pat = SimpleNamespace(revoked_at=None, expires_at=None, last_used_at=None)
        user = SimpleNamespace(is_active=False)
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value.first.return_value = (
            pat,
            user,
        )

        result = PATService(db).validate(raw)

        self.assertEqual(result.failure, PATValidationFailure.INACTIVE_USER)


class PATAuthenticationTests(TestCase):
    def setUp(self):
        stub_permissions(self)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_valid_pat_resolves_user_with_read_permission(self, service):
        user = SimpleNamespace(id=uuid4(), is_active=True)
        pat = SimpleNamespace(
            id=uuid4(),
            user_id=user.id,
            permissions=["entries.view"],
        )
        service.return_value.validate.return_value = PATValidationResult(
            token=pat,
            user=user,
        )
        raw = PAT_MARKER + "x" * 32
        req = request(authorization=f"Bearer {raw}")

        result = auth_module.get_current_user(req, credentials(raw), MagicMock())

        self.assertIs(result, user)
        self.assertEqual(req.state.auth_method, "pat")
        service.return_value.touch_last_used.assert_called_once_with(pat)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_read_only_pat_cannot_write(self, service):
        user = SimpleNamespace(id=uuid4(), is_active=True)
        pat = SimpleNamespace(
            id=uuid4(),
            user_id=user.id,
            permissions=["entries.view"],
        )
        service.return_value.validate.return_value = PATValidationResult(
            token=pat,
            user=user,
        )
        raw = PAT_MARKER + "x" * 32

        with self.assertRaises(HTTPException) as caught:
            auth_module.get_current_user(
                request(path="/api/entries/upload", method="POST"),
                credentials(raw),
                MagicMock(),
            )

        self.assertEqual(caught.exception.status_code, 403)
        # a denied request is not token activity
        service.return_value.touch_last_used.assert_not_called()

    def _authenticate(self, service, permissions, path, method, is_admin=False):
        user = SimpleNamespace(
            id=uuid4(),
            is_active=True,
            email="u@corp",
            is_system=False,
        )
        pat = SimpleNamespace(id=uuid4(), user_id=user.id, permissions=permissions)
        service.return_value.validate.return_value = PATValidationResult(
            token=pat,
            user=user,
        )
        raw = PAT_MARKER + "x" * 32
        with patch("app.core.auth.is_admin_user", return_value=is_admin):
            return auth_module.get_current_user(
                request(path=path, method=method),
                credentials(raw),
                MagicMock(),
            )

    def _status(self, *args, **kwargs):
        with self.assertRaises(HTTPException) as caught:
            self._authenticate(*args, **kwargs)
        return caught.exception.status_code

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_non_admin_pat_on_admin_path_gets_404_whatever_its_scopes(self, service):
        # admin:read can be attached to anyone's token, so the scope alone never
        # settles it. Answering here rather than leaving it to require_admin
        # keeps the admin area undiscoverable *and* keeps a probe that was going
        # to be refused out of the token's usage record.
        for permissions in ([], ["admin.view"]):
            with self.subTest(permissions=permissions):
                self.assertEqual(
                    self._status(service, permissions, "/api/admin/stats", "GET"),
                    404,
                )
                service.return_value.touch_last_used.assert_not_called()

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_interactive_only_admin_reads_never_count_as_usage(self, service):
        # These two manage credentials rather than report on them, so their
        # routes require an interactive login. Refusing at the token gate means
        # the rejection happens before touch_last_used, not after it.
        for path in ("/api/admin/pats", "/api/admin/pat-users"):
            with self.subTest(path=path):
                self.assertEqual(
                    self._status(
                        service,
                        ["admin.view"],
                        path,
                        "GET",
                        is_admin=True,
                    ),
                    403,
                )
                service.return_value.touch_last_used.assert_not_called()

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_admin_pat_without_admin_scope_gets_403(self, service):
        self.assertEqual(
            self._status(service, [], "/api/admin/stats", "GET", is_admin=True),
            403,
        )

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_admin_pat_with_admin_scope_reads_admin_data(self, service):
        user = self._authenticate(
            service,
            ["admin.view"],
            "/api/admin/stats",
            "GET",
            is_admin=True,
        )
        self.assertTrue(user.is_active)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_no_scope_grants_admin_mutations_to_a_pat(self, service):
        # Admin writes manage accounts and credentials; there is no admin:write.
        for path, method in (
            ("/api/admin/users/123/active", "PATCH"),
            ("/api/admin/users/123/pats", "POST"),
            ("/api/admin/pats/123", "DELETE"),
        ):
            with self.subTest(path=path, method=method):
                status = self._status(
                    service,
                    ["admin.view"],
                    path,
                    method,
                    is_admin=True,
                )
                self.assertEqual(status, 403)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_unmapped_routes_are_denied_to_pats(self, service):
        # Default deny: a new router is not PAT-callable until it is mapped.
        for path, method in (
            ("/api/auth/pats", "GET"),
            ("/api/auth/logout", "POST"),
            ("/api/something-new", "GET"),
        ):
            with self.subTest(path=path, method=method):
                self.assertEqual(self._status(service, [], path, method), 403)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_me_needs_no_scope(self, service):
        user = self._authenticate(service, [], "/api/auth/me", "GET")
        self.assertTrue(user.is_active)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_capability_mapping_per_route(self, service):
        cases = (
            ("/api/entries/", "GET", Capability.ENTRIES_VIEW),
            ("/api/entries/1/chat", "POST", Capability.ENTRIES_CHAT),
            ("/api/entries/upload", "POST", Capability.ENTRIES_UPLOAD),
            ("/api/entries/1/summary", "POST", Capability.ENTRIES_SUMMARIZE),
            ("/api/projects/", "POST", Capability.PROJECTS_CREATE),
            ("/api/projects/1/members", "POST", Capability.PROJECTS_MANAGE),
            ("/api/prompt-templates/", "GET", Capability.TEMPLATES_USE),
            ("/api/prompt-templates/1", "DELETE", Capability.TEMPLATES_MANAGE),
        )
        for path, method, cap in cases:
            with self.subTest(path=path, method=method):
                self._authenticate(
                    service,
                    [cap.value],
                    path,
                    method,
                    is_admin=True,
                )  # must not raise
                other = [c.value for c in ALL_CAPABILITIES if c is not cap]
                self.assertEqual(
                    self._status(service, other, path, method, is_admin=True),
                    403,
                )

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_token_never_exceeds_its_owner(self, service):
        # templates.manage is not in the Everyone defaults the stub hands out.
        self.assertEqual(
            self._status(
                service,
                ["templates.manage"],
                "/api/prompt-templates/1",
                "DELETE",
            ),
            403,
        )
        service.return_value.touch_last_used.assert_not_called()

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_legacy_scope_names_still_work(self, service):
        self._authenticate(service, ["entries:read"], "/api/entries/1/chat", "POST")

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.PATService")
    def test_project_listing_needs_no_capability(self, service):
        self._authenticate(service, [], "/api/projects/", "GET")

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.logger")
    @patch("app.core.auth.PATService")
    def test_invalid_pat_returns_401_and_logs_without_raw_token(self, service, logger):
        service.return_value.validate.return_value = PATValidationResult(
            failure=PATValidationFailure.INVALID,
        )
        raw = PAT_MARKER + "secret-value-that-must-not-be-logged"

        with self.assertRaises(HTTPException) as caught:
            auth_module.get_current_user(request(), credentials(raw), MagicMock())

        self.assertEqual(caught.exception.status_code, 401)
        logged = " ".join(str(value) for value in logger.warning.call_args.args)
        self.assertNotIn(raw, logged)
        self.assertIn(raw[:16], logged)

    @patch.object(auth_module.settings, "auth_mode", AuthMode.OIDC)
    @patch("app.core.auth.logger")
    def test_missing_credentials_returns_401_and_is_logged(self, logger):
        with self.assertRaises(HTTPException) as caught:
            auth_module.get_current_user(request(), None, MagicMock())

        self.assertEqual(caught.exception.status_code, 401)
        self.assertIn("missing", logger.warning.call_args.args)


class PATUpdateSchemaTests(TestCase):
    def test_only_sent_fields_count_as_changes(self):
        from app.models.schemas import PersonalAccessTokenUpdate

        self.assertEqual(
            PersonalAccessTokenUpdate(name=" CI ").changes(),
            {"name": "CI"},
        )
        self.assertEqual(
            PersonalAccessTokenUpdate.model_validate({"expires_at": None}).changes(),
            {"expires_at": None},
        )
        self.assertEqual(PersonalAccessTokenUpdate().changes(), {})

    def test_rejects_past_expiry_and_blank_name(self):
        from pydantic import ValidationError

        from app.models.schemas import PersonalAccessTokenUpdate

        with self.assertRaises(ValidationError):
            PersonalAccessTokenUpdate(expires_at=utcnow() - timedelta(minutes=1))
        with self.assertRaises(ValidationError):
            PersonalAccessTokenUpdate(name="   ")
