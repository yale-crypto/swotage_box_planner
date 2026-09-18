"""
Asset delivery and liveness: the self-hosted vendor bundle and /healthz.

Run with:  pytest tests/ -v
"""

import sys, os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from webapp import app as webapp

BUNDLE = "plotly-gl3d-2.35.2.min.js"


@pytest.fixture
def client():
    webapp.app.config.update(TESTING=True)
    return webapp.app.test_client()


class TestHealthz:
    def test_reports_ok(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.get_json() == {"ok": True}

    def test_is_cheaper_than_the_page(self, client):
        """It is pinged every few minutes, so it must not render a template."""
        assert len(client.get("/healthz").data) < len(client.get("/").data) / 10


class TestVendorAssets:
    def test_serves_precompressed_when_accepted(self, client):
        r = client.get(f"/vendor/{BUNDLE}", headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert r.headers["Content-Encoding"] == "gzip"
        # The type must describe the decoded body, not the gzip wrapper.
        assert "javascript" in r.headers["Content-Type"]
        assert "Accept-Encoding" in r.headers["Vary"]

    def test_compression_is_worth_having(self, client):
        gz = client.get(f"/vendor/{BUNDLE}", headers={"Accept-Encoding": "gzip"})
        raw = client.get(f"/vendor/{BUNDLE}", headers={"Accept-Encoding": "identity"})
        assert "Content-Encoding" not in raw.headers
        assert len(gz.data) < len(raw.data) / 2

    def test_version_pinned_urls_are_cached_hard(self, client):
        cache = client.get(f"/vendor/{BUNDLE}").headers["Cache-Control"]
        assert "immutable" in cache and "max-age=31536000" in cache

    def test_revisit_is_a_304(self, client):
        first = client.get(f"/vendor/{BUNDLE}", headers={"Accept-Encoding": "gzip"})
        again = client.get(f"/vendor/{BUNDLE}", headers={
            "Accept-Encoding": "gzip", "If-None-Match": first.headers["ETag"]})
        assert again.status_code == 304
        assert not again.data

    def test_missing_file_is_404(self, client):
        assert client.get("/vendor/not-a-real-bundle.js").status_code == 404

    @pytest.mark.parametrize("attack", [
        "../app.py",
        "..%2Fapp.py",
        "....//app.py",
        "../../../etc/passwd",
    ])
    def test_cannot_escape_the_vendor_directory(self, client, attack):
        r = client.get(f"/vendor/{attack}")
        assert r.status_code in (301, 308, 400, 404)
        assert b"Flask" not in r.data and b"root:" not in r.data


class TestPageWiring:
    def test_page_loads_the_vendored_bundle_not_a_cdn(self, client):
        html = client.get("/").get_data(as_text=True)
        assert f'src="/vendor/{BUNDLE}"' in html
        assert "cdn.plot.ly" not in html

    def test_bundle_is_deferred(self, client):
        """A 0.5 MB script in <head> must not block first paint."""
        html = client.get("/").get_data(as_text=True)
        tag = html[html.index("/vendor/") - 200 : html.index("/vendor/") + 80]
        assert "defer" in tag
