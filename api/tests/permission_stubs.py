"""Capability evaluation without a database, for tests that mock the DB."""

from unittest.mock import patch

from app.core.capabilities import DEFAULT_EVERYONE
from app.services.permission_service import FULL, Effective, PermissionService


def _effective(self, user):
    from app.core.auth import is_admin_user

    if is_admin_user(user):
        return FULL
    return Effective(global_caps=frozenset(DEFAULT_EVERYONE))


def stub_permissions(testcase):
    """Admins hold everything, everybody else the Everyone defaults."""

    patcher = patch.object(PermissionService, "effective", _effective)
    patcher.start()
    testcase.addCleanup(patcher.stop)
