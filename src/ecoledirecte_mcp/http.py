# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""HTTP transport for the read-only Ecole Directe MCP server.

The server binds to loopback only.  A reverse proxy or tunnel may terminate TLS
and forward requests; every request must still carry the private API key as
``Authorization: Bearer <key>``.  Allowed hosts and origins come from
``ED_HTTP_ALLOWED_HOSTS`` — loopback aside, nothing is hardcoded.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import ConfigError, Settings, assert_private_file
from .server import build_server

_MAX_BODY = 1024 * 1024
_API_KEY_MIN_LENGTH = 32
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_LOOPBACK_HOST_PATTERNS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
_LOOPBACK_ORIGIN_PATTERNS = tuple(
    f"{scheme}://{host}"
    for scheme in ("http", "https")
    for host in _LOOPBACK_HOST_PATTERNS
)


class ApiKeyMiddleware:
    """Pure ASGI bearer-token gate (safe for streaming responses)."""

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app = app
        self._key = api_key.encode("utf-8")

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        authorization = headers.get("authorization", "")
        scheme, _, candidate = authorization.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            candidate.encode("utf-8"), self._key
        ):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["cache-control"] = "no-store"
                response_headers["x-content-type-options"] = "nosniff"
                response_headers["referrer-policy"] = "no-referrer"
            await send(message)

        await self.app(scope, receive, secure_send)


def load_api_key() -> str:
    """Load the private key from a 0600 file, or from the environment."""
    path_value = os.environ.get("ED_HTTP_API_KEY_FILE")
    if path_value:
        path = Path(path_value).expanduser()
        assert_private_file(path, "Clé API HTTP")
        try:
            key = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"Clé API HTTP illisible ({path}): {exc}") from exc
    else:
        key = os.environ.get("ED_HTTP_API_KEY", "").strip()

    if len(key) < _API_KEY_MIN_LENGTH:
        raise ConfigError(
            "Clé API HTTP absente ou trop courte. Définis ED_HTTP_API_KEY_FILE "
            "vers un fichier 0600 contenant au moins 32 caractères."
        )
    return key


def _env_list(name: str) -> list[str]:
    """Split a comma-separated environment variable, ignoring empty items."""
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _resolve_allowlist() -> tuple[list[str], list[str]]:
    """Return ``(allowed_hosts, allowed_origins)``.

    Only loopback is accepted by default.  ``ED_HTTP_ALLOWED_HOSTS`` adds
    entries: ``host[:port]`` allows the host and derives its ``http``/``https``
    origins, while an entry carrying a scheme only adds that exact origin.
    """
    hosts = list(_LOOPBACK_HOST_PATTERNS)
    origins = list(_LOOPBACK_ORIGIN_PATTERNS)

    for entry in _env_list("ED_HTTP_ALLOWED_HOSTS"):
        if "://" not in entry:
            hosts.append(entry)
            origins.extend(f"{scheme}://{entry}" for scheme in ("https", "http"))
            continue
        origins.append(entry)
        netloc = urlsplit(entry).netloc
        if netloc:
            hosts.append(netloc)

    return hosts, origins


def build_http_app(server: MCPServer, api_key: str) -> ASGIApp:
    """Wrap the MCP Streamable HTTP app with the API-key gate."""
    allowed_hosts, allowed_origins = _resolve_allowlist()
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=False,
        stateless_http=False,
        max_request_body_size=_MAX_BODY,
        session_idle_timeout=900.0,
        max_sessions=20,
        host="127.0.0.1",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )
    return ApiKeyMiddleware(app, api_key)


def create_app() -> ASGIApp:
    """Uvicorn factory: fresh settings and session per process."""
    settings = Settings.from_env()
    return build_http_app(build_server(settings), load_api_key())


def main() -> None:
    """Run the MCP server over HTTP on loopback only."""
    host = os.environ.get("ED_HTTP_HOST", "127.0.0.1")
    if host not in _LOOPBACK_HOSTS:
        raise ConfigError("ED_HTTP_HOST doit être une adresse de bouclage.")
    try:
        port = int(os.environ.get("ED_HTTP_PORT", "8765"))
    except ValueError as exc:
        raise ConfigError("ED_HTTP_PORT doit être un entier.") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("ED_HTTP_PORT doit être compris entre 1 et 65535.")

    uvicorn.run(
        "ecoledirecte_mcp.http:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=os.environ.get("ED_LOG_LEVEL", "warning").lower(),
        access_log=False,
        server_header=False,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":  # pragma: no cover
    main()

