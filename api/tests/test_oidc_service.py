import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services import oidc_service
from app.services.oidc_service import OIDCError, extract_claims, redirect_uri


class ExtractClaimsTests(TestCase):
    def test_maps_default_claims(self):
        claims = {
            "iss": "https://idp.test",
            "sub": "user-1",
            "email": "User@Test",
            "name": "Test User",
        }
        result = extract_claims(claims)
        self.assertEqual(
            result,
            {
                "issuer": "https://idp.test",
                "subject": "user-1",
                "email": "User@Test",
                "display_name": "Test User",
            },
        )

    @patch.object(oidc_service.settings, "oidc_claim_email", "upn")
    def test_supports_adfs_upn_mapping(self):
        claims = {"iss": "https://fs.test", "sub": "u", "upn": "user@corp", "name": "U"}
        self.assertEqual(extract_claims(claims)["email"], "user@corp")

    def test_missing_required_claim_raises_with_code(self):
        with self.assertRaises(OIDCError) as ctx:
            extract_claims({"iss": "https://idp.test", "sub": "u", "name": "x"})
        self.assertEqual(ctx.exception.code, "missing_claim")

    def test_missing_name_falls_back_to_none(self):
        claims = {"iss": "https://idp.test", "sub": "u", "email": "a@b"}
        self.assertIsNone(extract_claims(claims)["display_name"])


class RedirectUriTests(TestCase):
    @patch.object(oidc_service.settings, "public_base_url", "https://vv.test/")
    def test_builds_callback_url_without_double_slash(self):
        self.assertEqual(redirect_uri(), "https://vv.test/api/auth/oidc/callback")
