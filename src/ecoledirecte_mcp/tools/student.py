# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Student profile, timeline and class tools."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean
from ecoledirecte_api.exceptions import BaseEcoleDirecteException

from ..validation import require_numeric_id
from ._common import PROFILE_TTL, cached, class_id_for, resolve_student


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_get_profile",
        description=(
            "Profil complet de l'élève : identité, coordonnées, classe, "
            "établissement, photo, responsables et options."
        ),
    )
    async def ed_get_profile(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(
            await cached(f"profile|{sid}", PROFILE_TTL, ep.get_student, sid)
        )

    @server.tool(
        name="ed_get_timeline",
        description=(
            "Fil d'actualité personnel de l'élève : nouvelles notes, absences, "
            "documents, messages (date, type, titre, contenu)."
        ),
    )
    async def ed_get_timeline(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(
            await cached(
                f"timeline|{sid}", PROFILE_TTL, ep.get_timeline, sid
            )
        )

    @server.tool(
        name="ed_get_school_timeline",
        description=(
            "Fil d'accueil commun de l'établissement et post-its (informations "
            "de la vie scolaire, événements)."
        ),
    )
    async def ed_get_school_timeline(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(
            await cached(
                f"school-timeline|{sid}", PROFILE_TTL, ep.get_common_timeline, sid
            )
        )

    @server.tool(
        name="ed_list_manuals",
        description="Manuels numériques associés à l'élève (titre, éditeur, URL).",
    )
    async def ed_list_manuals(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(
            await cached(f"manuals|{sid}", PROFILE_TTL, ep.get_manuals, sid)
        )

    @server.tool(
        name="ed_list_visios",
        description="Sessions de visioconférence visibles par l'élève.",
    )
    async def ed_list_visios(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(await cached(f"visios|{sid}", 120.0, ep.get_visios, sid))

    @server.tool(
        name="ed_list_qcms",
        description="QCM / évaluations associés au compte élève.",
    )
    async def ed_list_qcms(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(await cached(f"qcms|{sid}", 300.0, ep.get_qcms, sid))

    @server.tool(
        name="ed_get_class_life",
        description=(
            "Vie de la classe : professeurs, délégués, projets, informations "
            "collectives. Les deux routes Ecole Directe sont interrogées."
        ),
    )
    async def ed_get_class_life(
        classe_id: str | None = None, student_id: str | None = None
    ) -> Any:
        sid = await resolve_student(student_id)
        classe = (
            require_numeric_id(classe_id, "classe_id")
            if classe_id
            else class_id_for(sid)
        )
        return clean(
            await cached(
                f"class-life|{classe}", 300.0, ep.get_class_life, classe
            )
        )

    @server.tool(
        name="ed_list_class_students",
        description=(
            "Liste des élèves d'une classe (si l'établissement l'autorise pour "
            "les comptes élèves)."
        ),
    )
    async def ed_list_class_students(
        classe_id: str | None = None, student_id: str | None = None
    ) -> Any:
        sid = await resolve_student(student_id)
        classe = (
            require_numeric_id(classe_id, "classe_id")
            if classe_id
            else class_id_for(sid)
        )
        try:
            data = await cached(
                f"class-students|{classe}", 600.0, ep.get_class_students, classe
            )
        except BaseEcoleDirecteException:
            return {
                "classe_id": classe,
                "count": 0,
                "students": [],
                "message": "Liste des élèves non autorisée pour un compte élève.",
            }
        return clean(data)
