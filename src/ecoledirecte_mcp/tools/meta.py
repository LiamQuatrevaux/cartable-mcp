# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Escape hatch and catalog tools."""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..runtime import get_session
from ..validation import require_text

_PATH_RE = re.compile(r"^/[A-Za-z0-9_./{}-]+\.awp$")
_PATH_MAX = 200
_DENIED_PREFIXES = (
    "/login.awp",
    "/renewtoken.awp",
    "/connexion/",
    "/telechargement.awp",
    "/televersement.awp",
)
_PARAM_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")
_BODY_MAX = 20_000

CATALOG: dict[str, list[str]] = {
    "session": [
        "ed_auth_status",
        "ed_login",
        "ed_submit_qcm",
        "ed_logout",
        "ed_select_account",
        "ed_get_context",
        "ed_health",
    ],
    "élève": [
        "ed_get_profile",
        "ed_get_timeline",
        "ed_get_school_timeline",
        "ed_list_manuals",
        "ed_list_visios",
        "ed_list_qcms",
        "ed_get_class_life",
        "ed_list_class_students",
    ],
    "notes": [
        "ed_list_periods",
        "ed_get_period_report",
        "ed_list_subject_grades",
        "ed_list_evaluations",
        "ed_list_competences",
        "ed_get_annual_summary",
    ],
    "cahier de textes": [
        "ed_list_homework",
        "ed_get_homework_day",
        "ed_list_homework_subjects",
        "ed_get_homework_index",
    ],
    "emploi du temps": [
        "ed_get_timetable",
        "ed_get_today",
        "ed_get_week",
        "ed_get_next_course",
        "ed_list_timetable_changes",
    ],
    "vie scolaire": [
        "ed_get_vie_scolaire",
        "ed_list_absences",
        "ed_list_retards",
        "ed_list_sanctions",
        "ed_list_encouragements",
        "ed_get_attendance_summary",
        "ed_get_carnet_correspondance",
        "ed_list_sessions_rdv",
    ],
    "messagerie": [
        "ed_list_messages",
        "ed_get_message",
        "ed_download_message_attachment",
    ],
    "documents": [
        "ed_list_documents",
        "ed_list_pieces_a_verser",
        "ed_get_wallet_balances",
        "ed_download_document",
        "ed_list_forms",
        "ed_get_form",
        "ed_list_surveys",
    ],
    "cantine": [
        "ed_get_menus",
        "ed_list_canteen_points",
        "ed_list_canteen_orders",
        "ed_check_canteen_slot",
    ],
    "espaces & cloud": [
        "ed_list_workspaces",
        "ed_get_workspace",
        "ed_list_workspace_activities",
        "ed_get_workspace_activity",
        "ed_list_workspace_postits",
        "ed_list_cloud",
        "ed_download_cloud_file",
    ],
    "méta": ["ed_get_catalog", "ed_raw_query"],
}


def is_allowed_path(path: str) -> bool:
    """Only simple .awp paths are accepted, never auth or upload routes."""
    if not path.startswith("/") or len(path) > _PATH_MAX:
        return False
    if ".." in path or "//" in path or "\\" in path:
        return False
    if any(path.startswith(prefix) for prefix in _DENIED_PREFIXES):
        return False
    return bool(_PATH_RE.fullmatch(path))


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_get_catalog",
        description=(
            "Catalogue des données Ecole Directe disponibles, groupées par "
            "domaine, avec le nom du tool à appeler pour chacune."
        ),
    )
    async def ed_get_catalog() -> dict[str, Any]:
        return {
            "read_only": True,
            "domains": CATALOG,
            "tool_count": sum(len(tools) for tools in CATALOG.values()),
        }

    @server.tool(
        name="ed_raw_query",
        description=(
            "Requête GET brute en lecture seule sur un endpoint .awp non couvert "
            "(ex: /eleves/123/timeline.awp). Les routes d'authentification, "
            "d'upload, de téléchargement et les verbes d'écriture sont refusés."
        ),
    )
    async def ed_raw_query(
        path: str,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        candidate = require_text(path.strip(), "path", _PATH_MAX)
        if not is_allowed_path(candidate):
            raise ValueError(
                "Chemin refusé : seuls les chemins .awp de lecture sont autorisés."
            )

        safe_params: dict[str, str] = {}
        for key, value in (params or {}).items():
            if key.lower() in {"verbe", "v"}:
                continue
            if not _PARAM_RE.fullmatch(key):
                raise ValueError(f"Nom de paramètre refusé : {key!r}.")
            safe_params[key] = require_text(value, f"paramètre {key}", 200)

        if body is not None:
            encoded = json.dumps(body, ensure_ascii=False)
            if len(encoded) > _BODY_MAX:
                raise ValueError("Corps de requête trop volumineux.")

        payload = await get_session().run(
            ep._get, candidate, data=body, params=safe_params
        )
        return clean(payload)
