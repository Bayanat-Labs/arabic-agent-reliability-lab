from fastapi.testclient import TestClient

from bayanat_lab.dashboard import create_dashboard_app


def test_dashboard_is_rtl_read_only_and_asset_local(tmp_path):
    client = TestClient(create_dashboard_app(tmp_path))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True, "mode": "read-only", "external_assets": False}
    page = client.get("/")
    assert page.status_code == 200
    assert 'lang="ar"' in page.text
    assert 'dir="rtl"' in page.text
    assert "https://" not in page.text
    assert "http://" not in page.text


def test_dashboard_rejects_path_traversal(tmp_path):
    client = TestClient(create_dashboard_app(tmp_path))
    assert client.get("/passport/%2E%2E%5Csecret").status_code == 404
