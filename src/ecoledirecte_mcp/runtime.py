# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Process-wide session singleton used by the MCP tools."""

from __future__ import annotations

from .session import EdSession

_SESSION: EdSession | None = None


def set_session(session: EdSession) -> None:
    """Install the session created at server startup."""
    global _SESSION
    _SESSION = session


def get_session() -> EdSession:
    """Return the active session."""
    if _SESSION is None:  # pragma: no cover - always set by build_server
        raise RuntimeError("Session Ecole Directe non initialisée.")
    return _SESSION


def reset_session() -> None:
    """Drop the session (used by tests)."""
    global _SESSION
    _SESSION = None
