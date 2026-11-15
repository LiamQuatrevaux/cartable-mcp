# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Strict validation of tool inputs before they reach a URL or a file path."""

from __future__ import annotations

import re
from datetime import date as date_type

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_RE = re.compile(r"^\d{4}-\d{4}$")
_NUMERIC_ID_RE = re.compile(r"^[0-9]{1,20}$")
_TOKEN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def require_date(value: str, field: str = "date") -> str:
    """Validate an ISO date and reject path metacharacters."""
    if not isinstance(value, str) or not _DATE_RE.match(value.strip()):
        raise ValueError(f"{field} doit être une date AAAA-MM-JJ.")
    candidate = value.strip()
    try:
        date_type.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} n'est pas une date valide : {candidate}.") from exc
    return candidate


def require_range(start: str, end: str) -> tuple[str, str]:
    """Validate an ordered ISO date range."""
    first = require_date(start, "date_debut")
    last = require_date(end, "date_fin")
    if first > last:
        raise ValueError("date_debut doit précéder date_fin.")
    return first, last


def require_year(value: str | None, field: str = "annee") -> str | None:
    """Validate a school year (AAAA-AAAA) when provided."""
    if value is None or value == "":
        return None
    candidate = value.strip()
    if not _YEAR_RE.match(candidate):
        raise ValueError(f"{field} doit être au format AAAA-AAAA.")
    start, end = (int(part) for part in candidate.split("-"))
    if end != start + 1:
        raise ValueError(f"{field} doit couvrir deux années consécutives.")
    return candidate


def require_numeric_id(value: str, field: str = "id") -> str:
    """Validate an opaque numeric identifier."""
    if not isinstance(value, str) or not _NUMERIC_ID_RE.match(value.strip()):
        raise ValueError(f"{field} doit être un identifiant numérique.")
    return value.strip()


def require_token_id(value: str, field: str = "id") -> str:
    """Validate an identifier made of letters, digits, '-' or '_'."""
    if not isinstance(value, str) or not _TOKEN_ID_RE.match(value.strip()):
        raise ValueError(f"{field} contient des caractères interdits.")
    return value.strip()


def require_text(value: str | None, field: str, max_length: int) -> str:
    """Validate a free-text query without control characters."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{field} doit être une chaîne.")
    if _CONTROL_RE.search(value):
        raise ValueError(f"{field} contient des caractères de contrôle.")
    if len(value) > max_length:
        raise ValueError(f"{field} dépasse {max_length} caractères.")
    return value


def require_choice(value: str, field: str, allowed: set[str]) -> str:
    """Validate an enumerated value."""
    if value not in allowed:
        raise ValueError(
            f"{field} invalide : {value}. Valeurs possibles : "
            + ", ".join(sorted(allowed))
        )
    return value


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Bound an integer coming from the agent."""
    return max(minimum, min(maximum, int(value)))


def require_remote_path(value: str, field: str = "chemin") -> str:
    """Validate a server-side UNC path used only as a query parameter."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} est vide.")
    if len(value) > 1024 or _CONTROL_RE.search(value):
        raise ValueError(f"{field} invalide ou trop long.")
    return value.strip()
