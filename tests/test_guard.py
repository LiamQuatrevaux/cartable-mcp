"""Les échecs attendus remontent avec leur message, pas « Error executing tool »."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ecoledirecte_api.exceptions import EcoleDirecteException
from ecoledirecte_mcp.guard import as_tool_error, guard
from ecoledirecte_mcp.session import AuthRequired


def test_guard_turns_value_error_into_tool_error() -> None:
    @guard
    async def boom() -> None:
        raise ValueError("student_id doit être un identifiant numérique.")

    with pytest.raises(ToolError, match="identifiant numérique"):
        asyncio.run(boom())


def test_guard_turns_auth_error_into_tool_error() -> None:
    @guard
    async def boom() -> None:
        raise AuthRequired("Aucun élève associé au compte.")

    with pytest.raises(ToolError, match="Aucun élève associé"):
        asyncio.run(boom())


def test_guard_lets_unexpected_crashes_through() -> None:
    @guard
    async def boom() -> None:
        raise RuntimeError("boum")

    with pytest.raises(RuntimeError, match="boum"):
        asyncio.run(boom())


def test_api_errors_keep_path_and_status() -> None:
    translated = as_tool_error(
        EcoleDirecteException(
            path="/eleves/1/notes.awp", status=500, message="Erreur serveur"
        )
    )

    assert isinstance(translated, ToolError)
    assert "/eleves/1/notes.awp" in str(translated)
    assert "500" in str(translated)
