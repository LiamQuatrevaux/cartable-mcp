# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Vie scolaire, carnet de correspondance and RDV tools."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..shaping import as_dict, attendance
from ._common import LIFE_TTL, cached, resolve_student


def _justified(item: dict[str, Any]) -> bool | None:
    value = item.get("justifiee", item.get("justifie"))
    if value is None:
        return None
    return value is True or str(value).lower() in {"1", "true", "oui"}


def register(server: MCPServer) -> None:
    async def _vie_scolaire(sid: str) -> Any:
        return clean(
            await cached(f"vs|{sid}", LIFE_TTL, ep.get_vie_scolaire, sid)
        )

    @server.tool(
        name="ed_get_vie_scolaire",
        description=(
            "Vie scolaire complète : absences, retards, sanctions, "
            "encouragements, dispenses et paramètres de confidentialité."
        ),
    )
    async def ed_get_vie_scolaire(
        student_id: str | None = None,
    ) -> Any:
        return await _vie_scolaire(resolve_student(student_id))

    @server.tool(
        name="ed_list_absences",
        description="Absences avec date, demi-journées, motif et justification.",
    )
    async def ed_list_absences(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        data = attendance(await _vie_scolaire(sid))
        return {"count": len(data["absences"]), "absences": data["absences"]}

    @server.tool(
        name="ed_list_retards",
        description="Retards avec date, durée, motif et justification.",
    )
    async def ed_list_retards(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        data = attendance(await _vie_scolaire(sid))
        return {"count": len(data["retards"]), "retards": data["retards"]}

    @server.tool(
        name="ed_list_sanctions",
        description="Sanctions disciplinaires visibles par l'élève.",
    )
    async def ed_list_sanctions(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        data = attendance(await _vie_scolaire(sid))
        return {"count": len(data["sanctions"]), "sanctions": data["sanctions"]}

    @server.tool(
        name="ed_list_encouragements",
        description="Encouragements et félicitations enregistrés.",
    )
    async def ed_list_encouragements(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        data = attendance(await _vie_scolaire(sid))
        return {
            "count": len(data["encouragements"]),
            "encouragements": data["encouragements"],
        }

    @server.tool(
        name="ed_get_attendance_summary",
        description=(
            "Bilan de présence : nombre d'absences et de retards, justifiés et "
            "non justifiés, sanctions et encouragements."
        ),
    )
    async def ed_get_attendance_summary(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        data = attendance(await _vie_scolaire(sid))
        absences = data["absences"]
        retards = data["retards"]
        justified = sum(1 for item in absences if _justified(item) is True)
        unjustified = sum(1 for item in absences if _justified(item) is False)
        return {
            "absences": {
                "total": len(absences),
                "justifiees": justified,
                "non_justifiees": unjustified,
                "sans_statut": len(absences) - justified - unjustified,
            },
            "retards": {"total": len(retards)},
            "sanctions": len(data["sanctions"]),
            "encouragements": len(data["encouragements"]),
            "dispenses": len(data["dispenses"]),
        }

    @server.tool(
        name="ed_get_carnet_correspondance",
        description=(
            "Carnet de correspondance : échanges avec l'établissement et suivis "
            "associés."
        ),
    )
    async def ed_get_carnet_correspondance(
        student_id: str | None = None,
    ) -> Any:
        sid = resolve_student(student_id)
        return clean(
            await cached(
                f"carnet|{sid}", LIFE_TTL, ep.get_carnet, sid
            )
        )

    @server.tool(
        name="ed_list_sessions_rdv",
        description=(
            "Sessions de rendez-vous (parents-professeurs, orientation) et "
            "informations d'invitation."
        ),
    )
    async def ed_list_sessions_rdv(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        data = clean(
            await cached(f"rdv|{sid}", LIFE_TTL, ep.get_sessions_rdv, sid)
        )
        payload = as_dict(data)
        sessions = payload.get("sessions") or payload.get("sessionsRdv") or data
        return {"sessions": sessions}
