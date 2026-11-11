from app.config import settings
from app.routes.analyze import _share_url
from app.services.file_hash import sha256_bytes


def test_sha256_bytes_is_stable_and_sized():
    first = sha256_bytes(b"identical pdf bytes")
    second = sha256_bytes(b"identical pdf bytes")
    assert first == second
    assert len(first) == 64
    assert sha256_bytes(b"different bytes") != first


def test_share_url_uses_configured_base(monkeypatch):
    monkeypatch.setattr(settings, "SHARE_BASE_URL", "https://n3level.id/")
    assert _share_url("abc123") == "https://n3level.id/share/abc123"


def test_share_url_is_none_without_base(monkeypatch):
    monkeypatch.setattr(settings, "SHARE_BASE_URL", "")
    assert _share_url("abc123") is None