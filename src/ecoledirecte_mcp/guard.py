# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Readable tool failures for the MCP server.

The MCP SDK hides any exception that is not a ``ToolError`` behind the opaque
message ``Error executing tool <name>``. Tool failures our user can act on
(validation, authentication, API errors) are therefore raised as
``ToolError`` with their real message; genuine crashes keep the SDK path and
their traceback.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ecoledirecte_api.exceptions import EcoleDirecteException

from .session import AuthRequired, SessionLimitError

LOGGER = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])
ToolFunc = Callable[..., Coroutine[Any, Any, Any]]


def _first_leaf(exc: BaseException) -> BaseException:
    """Unwrap ``ExceptionGroup`` layers, asyncio task groups may add."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def as_tool_error(exc: BaseException) -> ToolError | None:
    """Return a readable ``ToolError`` for a failure the user can act on."""
    exc = _first_leaf(exc)
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, (AuthRequired, SessionLimitError)):
        return ToolError(str(exc).strip() or type(exc).__name__)
    if isinstance(exc, EcoleDirecteException):
        return ToolError(str(exc).strip() or type(exc).__name__)
    if isinstance(exc, (ValueError, TypeError)):
        return ToolError(str(exc).strip() or type(exc).__name__)
    if isinstance(exc, (KeyError, IndexError, AttributeError)):
        return ToolError(f"{type(exc).__name__}: {exc}")
    return None


def guard(func: ToolFunc) -> ToolFunc:
    """Wrap one tool so expected failures reach the model with their message."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:
            translated = as_tool_error(exc)
            if translated is None:
                LOGGER.exception("échec inattendu de l'outil %s", func.__name__)
                raise
            raise translated from exc

    return wrapper


class CartableServer(MCPServer):
    """``MCPServer`` whose tools report failures with their real message."""

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        """Register a tool, wrapping its body in :func:`guard`."""
        register = super().tool(*args, **kwargs)

        def decorator(func: F) -> F:
            if not asyncio.iscoroutinefunction(func):
                return register(func)
            return cast(F, register(guard(cast(ToolFunc, func))))

        return decorator
