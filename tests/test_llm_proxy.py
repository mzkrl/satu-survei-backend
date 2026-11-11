"""Hermetic tests for the authenticated LLM passthrough (app.routes.llm_proxy).

The upstream 9router is replaced with a fake ``httpx.AsyncClient`` so these
tests never open a network connection.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.routes import llm_proxy
from app.utils.security import get_current_user

BASE_URL = "http://upstream.test/v1"
API_KEY = "server-side-key"


class FakeUpstreamResponse:
    """Minimal stand-in for an ``httpx.Response`` returned by ``send``."""

    def __init__(self, status_code=200, headers=None, chunks=(b"",)):
        self.status_code = status_code
        self.headers = httpx.Headers(headers or {"content-type": "application/json"})
        self.chunks = list(chunks)
        self.closed = False

    async def aiter_raw(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class FakeAsyncClient:
    """Records outgoing proxy requests and returns a canned upstream response."""

    def __init__(self, transport, timeout=None):
        self.transport = transport
        self.timeout = timeout
        self.requests = []
        self.sent = []
        self.closed = False

    def build_request(self, method, url, headers=None, content=None):
        request = SimpleNamespace(
            method=method,
            url=url,
            headers=dict(headers or {}),
            content=content,
        )
        self.requests.append(request)
        return request

    async def send(self, request, stream=False):
        self.sent.append(SimpleNamespace(request=request, stream=stream))
        if self.transport.error is not None:
            raise self.transport.error
        return self.transport.response

    async def aclose(self):
        self.closed = True


class FakeTransport:
    def __init__(self):
        self.response = FakeUpstreamResponse()
        self.error = None
        self.clients = []

    def AsyncClient(self, *args, **kwargs):
        client = FakeAsyncClient(self, **kwargs)
        self.clients.append(client)
        return client


def _header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _install_transport(monkeypatch):
    transport = FakeTransport()
    fake_httpx = SimpleNamespace(
        AsyncClient=transport.AsyncClient,
        Timeout=httpx.Timeout,
        HTTPError=httpx.HTTPError,
    )
    monkeypatch.setattr(llm_proxy, "httpx", fake_httpx)
    return transport


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    main.app.dependency_overrides.clear()


@pytest.fixture
def api():
    """TestClient whose auth dependency is stubbed out (no database access)."""

    def _fake_current_user():
        return SimpleNamespace(id="test-user")

    main.app.dependency_overrides[get_current_user] = _fake_current_user
    client = TestClient(main.app)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def proxy_settings(monkeypatch):
    monkeypatch.setattr(llm_proxy.settings, "LLM_PROXY_ENABLED", True)
    monkeypatch.setattr(llm_proxy.settings, "QWEN_BASE_URL", BASE_URL)
    monkeypatch.setattr(llm_proxy.settings, "QWEN_API_KEY", API_KEY)
    return llm_proxy.settings


# ---------------------------------------------------------------------------
# Auth and routing gates
# ---------------------------------------------------------------------------


def test_proxy_requires_authentication(proxy_settings):
    client = TestClient(main.app)
    try:
        response = client.get("/llm/models")
    finally:
        client.close()

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ["unknown", "chat", "chat/completions/extra"])
def test_disallowed_paths_return_404_without_upstream_call(
    path, api, proxy_settings, monkeypatch
):
    transport = _install_transport(monkeypatch)

    response = api.get(f"/llm/{path}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unsupported LLM endpoint"
    assert transport.clients == []


def test_disabled_proxy_returns_404_without_upstream_call(
    api, proxy_settings, monkeypatch
):
    monkeypatch.setattr(llm_proxy.settings, "LLM_PROXY_ENABLED", False)
    transport = _install_transport(monkeypatch)

    response = api.get("/llm/models")

    assert response.status_code == 404
    assert response.json()["detail"] == "LLM proxy disabled"
    assert transport.clients == []


# ---------------------------------------------------------------------------
# Forwarding behavior
# ---------------------------------------------------------------------------


def test_models_request_forwards_to_base_url_with_server_authorization(
    api, proxy_settings, monkeypatch
):
    transport = _install_transport(monkeypatch)
    transport.response = FakeUpstreamResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        chunks=[b'{"data": []}'],
    )
    monkeypatch.setattr(
        llm_proxy.settings, "QWEN_BASE_URL", BASE_URL + "/"
    )

    response = api.get(
        "/llm/models",
        headers={"Authorization": "Bearer client-token", "X-Request-Id": "rid-1"},
    )

    assert response.status_code == 200
    assert response.content == b'{"data": []}'
    assert len(transport.clients) == 1
    client = transport.clients[0]
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.method == "GET"
    assert request.url == f"{BASE_URL}/models"
    assert _header(request.headers, "authorization") == f"Bearer {API_KEY}"
    assert "client-token" not in _header(request.headers, "authorization")
    assert _header(request.headers, "x-request-id") == "rid-1"
    assert client.sent[0].stream is True
    assert client.closed is True
    assert transport.response.closed is True


def test_post_forwards_method_query_body_and_propagates_upstream_response(
    api, proxy_settings, monkeypatch
):
    transport = _install_transport(monkeypatch)
    upstream_body = b'{"id": "chatcmpl-1", "choices": []}'
    transport.response = FakeUpstreamResponse(
        status_code=201,
        headers={
            "content-type": "application/json; charset=utf-8",
            "content-length": "9999",
            "set-cookie": "secret=cookie",
            "connection": "keep-alive",
            "x-upstream": "yes",
        },
        chunks=[upstream_body[:10], upstream_body[10:]],
    )

    response = api.post(
        "/llm/chat/completions?trace=1",
        content=b'{"model": "m", "messages": []}',
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer client-token",
            "X-Custom": "custom-value",
        },
    )

    assert response.status_code == 201
    assert response.content == upstream_body
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    assert response.headers["x-upstream"] == "yes"
    assert "set-cookie" not in response.headers
    assert "connection" not in response.headers

    request = transport.clients[0].requests[0]
    assert request.method == "POST"
    assert request.url == f"{BASE_URL}/chat/completions?trace=1"
    assert request.content == b'{"model": "m", "messages": []}'
    assert _header(request.headers, "authorization") == f"Bearer {API_KEY}"
    assert _header(request.headers, "x-custom") == "custom-value"


def test_empty_server_api_key_does_not_forward_client_authorization(
    api, proxy_settings, monkeypatch
):
    monkeypatch.setattr(llm_proxy.settings, "QWEN_API_KEY", "")
    transport = _install_transport(monkeypatch)

    response = api.get(
        "/llm/models", headers={"Authorization": "Bearer client-token"}
    )

    assert response.status_code == 200
    request = transport.clients[0].requests[0]
    assert _header(request.headers, "authorization") is None
    assert all("client-token" not in value for value in request.headers.values())


def test_upstream_transport_error_returns_502_and_closes_client(
    api, proxy_settings, monkeypatch
):
    transport = _install_transport(monkeypatch)
    transport.error = httpx.ConnectError("upstream down")

    response = api.get("/llm/models")

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM upstream unavailable"
    assert transport.clients[0].closed is True