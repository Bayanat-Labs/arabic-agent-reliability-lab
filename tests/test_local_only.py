import pytest

from bayanat_lab.settings import require_loopback_host, require_loopback_url


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"],
)
def test_loopback_urls_are_accepted(url):
    assert require_loopback_url(url) == url


@pytest.mark.parametrize(
    "url",
    ["https://api.example.com", "http://192.168.1.5:11434", "file:///tmp/model"],
)
def test_remote_or_non_http_services_are_rejected(url):
    with pytest.raises(ValueError):
        require_loopback_url(url)


def test_dashboard_bind_rejects_lan_and_wildcard():
    assert require_loopback_host("127.0.0.1") == "127.0.0.1"
    with pytest.raises(ValueError):
        require_loopback_host("0.0.0.0")
