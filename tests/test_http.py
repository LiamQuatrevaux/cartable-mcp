import os
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import pytest

from ecoledirecte_mcp.config import ConfigError
from ecoledirecte_mcp.http import (
    ApiKeyMiddleware,
    _resolve_allowlist,
    load_api_key,
)


def test_load_api_key_requires_private_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions only")

    path = tmp_path / "api_key"
    path.write_text("k" * 48, encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setenv("ED_HTTP_API_KEY_FILE", str(path))
    monkeypatch.delenv("ED_HTTP_API_KEY", raising=False)

    assert load_api_key() == "k" * 48

    path.chmod(0o644)
    with pytest.raises(ConfigError, match="chmod 600"):
        load_api_key()


@pytest.mark.asyncio
async def test_api_key_middleware_rejects_and_accepts() -> None:
    sent: list[MutableMapping[str, Any]] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def call(headers: list[tuple[bytes, bytes]]) -> int:
        sent.clear()

        async def receive() -> Any:
            return {"type": "http.request", "body": b""}

        async def send(message: MutableMapping[str, Any]) -> None:
            sent.append(message)

        middleware = ApiKeyMiddleware(app, "k" * 48)
        await middleware({"type": "http", "headers": headers}, receive, send)
        return int(sent[0]["status"])

    assert await call([]) == 401
    assert await call([(b"authorization", b"Bearer wrong")]) == 401
    assert await call([(b"authorization", b"Bearer " + b"k" * 48)]) == 200


def test_allowlist_defaults_to_loopback_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ED_HTTP_ALLOWED_HOSTS", raising=False)

    hosts, origins = _resolve_allowlist()

    assert hosts == ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    assert "http://127.0.0.1:*" in origins
    assert "https://localhost:*" in origins


def test_allowlist_reads_hosts_and_derives_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ED_HTTP_ALLOWED_HOSTS", "mcp.example.org, https://mcp.example.net"
    )

    hosts, origins = _resolve_allowlist()

    assert "mcp.example.org" in hosts
    assert "https://mcp.example.org" in origins
    assert "http://mcp.example.org" in origins
    assert "mcp.example.net" in hosts
    assert "https://mcp.example.net" in origins
    assert "http://mcp.example.net" not in origins
    assert all("example" in item or "127.0.0.1" in item or "localhost" in item or "::1" in item for item in hosts + origins)
