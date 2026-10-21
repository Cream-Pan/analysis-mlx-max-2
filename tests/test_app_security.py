"""Dependency-free checks for local app security policy."""
from pathlib import Path
import re
import unittest

from services.security import (
    STATIC_ASSETS,
    is_allowed_upload_origin,
    parse_cors_origins,
)


class CorsOriginPolicyTests(unittest.TestCase):
    def test_parses_and_deduplicates_explicit_origins(self):
        self.assertEqual(
            parse_cors_origins(" https://one.example, ,https://two.example,https://one.example "),
            ("https://one.example", "https://two.example"),
        )

    def test_rejects_wildcard_origin(self):
        with self.assertRaises(ValueError):
            parse_cors_origins("https://one.example, *")

    def test_allows_missing_and_same_origin_requests(self):
        allowed = parse_cors_origins("")
        self.assertTrue(is_allowed_upload_origin(None, "http://127.0.0.1:5000", allowed))
        self.assertTrue(is_allowed_upload_origin(
            "http://127.0.0.1:5000", "http://127.0.0.1:5000", allowed
        ))

    def test_allows_configured_origin_and_rejects_other_origins(self):
        allowed = parse_cors_origins("https://analysis.example")
        self.assertTrue(is_allowed_upload_origin(
            "https://analysis.example", "http://127.0.0.1:5000", allowed
        ))
        self.assertFalse(is_allowed_upload_origin(
            "https://untrusted.example", "http://127.0.0.1:5000", allowed
        ))
        self.assertFalse(is_allowed_upload_origin(
            "null", "http://127.0.0.1:5000", allowed
        ))


class StaticAssetPolicyTests(unittest.TestCase):
    def test_allowlisted_assets_exist(self):
        project_root = Path(__file__).resolve().parents[1]
        missing = sorted(
            asset for asset in STATIC_ASSETS
            if not (project_root / asset).is_file()
        )
        self.assertEqual(missing, [])

    def test_private_application_files_are_not_allowlisted(self):
        self.assertNotIn("app.py", STATIC_ASSETS)
        self.assertNotIn("services/common.py", STATIC_ASSETS)
        self.assertNotIn("tests/test_app_security.py", STATIC_ASSETS)

    def test_page_loads_scripts_from_local_files_only(self):
        project_root = Path(__file__).resolve().parents[1]
        html = (project_root / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script\s+src="([^"]+)"', html)
        external_scripts = [url for url in scripts if url.startswith(("http://", "https://"))]
        self.assertEqual(external_scripts, [])
        self.assertTrue(set(scripts).issubset(STATIC_ASSETS))


if __name__ == "__main__":
    unittest.main()
