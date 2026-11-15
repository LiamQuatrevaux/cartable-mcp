# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Timetable tools."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep

from ..shaping import iso, timetable_items, today
from ..validation import clamp, require_range
from ._common import cached, resolve_student, session


def _week_bounds(current: date) -> tuple[str, str]:
    monday = current - timedelta(days=current.weekday())
    return iso(monday), iso(monday + timedelta(days=6))


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_get_timetable",
        description=(
            "Emploi du temps sur une plage de dates (format AAAA-MM-JJ) : "
            "matière, professeur, salle, début/fin, cours annulés ou modifiés."
        ),
    )
    async def ed_get_timetable(
        date_debut: str,
        date_fin: str,
        student_id: str | None = None,
    ) -> Any:
        sid = resolve_student(student_id)
        date_debut, date_fin = require_range(date_debut, date_fin)
        data = await cached(
            f"timetable|{sid}|{date_debut}|{date_fin}",
            120.0,
            ep.get_timetable,
            sid,
            date_debut,
            date_fin,
        )
        return {"from": date_debut, "to": date_fin, "courses": timetable_items(data)}

    @server.tool(
        name="ed_get_today",
        description="Emploi du temps du jour, dans le fuseau configuré.",
    )
    async def ed_get_today(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        current = iso(today(session().settings))
        data = await cached(
            f"timetable|{sid}|{current}|{current}",
            120.0,
            ep.get_timetable,
            sid,
            current,
            current,
        )
        return {"date": current, "courses": timetable_items(data)}

    @server.tool(
        name="ed_get_week",
        description="Emploi du temps de la semaine en cours (lundi → dimanche).",
    )
    async def ed_get_week(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        start, end = _week_bounds(today(session().settings))
        data = await cached(
            f"timetable|{sid}|{start}|{end}",
            120.0,
            ep.get_timetable,
            sid,
            start,
            end,
        )
        return {"from": start, "to": end, "courses": timetable_items(data)}

    @server.tool(
        name="ed_get_next_course",
        description="Prochain cours à venir dans les 21 jours.",
    )
    async def ed_get_next_course(student_id: str | None = None) -> Any:
        sid = resolve_student(student_id)
        current = today(session().settings)
        start = iso(current)
        end = iso(current + timedelta(days=21))
        data = await cached(
            f"timetable|{sid}|{start}|{end}",
            60.0,
            ep.get_timetable,
            sid,
            start,
            end,
        )
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        upcoming = [
            course
            for course in timetable_items(data)
            if str(course.get("debut") or "") >= now
            and not course.get("annule")
            and str(course.get("typeCours") or "").upper()
            not in {"CONGE", "EVENEMENT"}
            and str(course.get("matiere") or "").strip()
        ]
        return upcoming[0] if upcoming else {"message": "Aucun cours à venir."}

    @server.tool(
        name="ed_list_timetable_changes",
        description=(
            "Cours annulés ou modifiés sur les prochains jours (par défaut 14)."
        ),
    )
    async def ed_list_timetable_changes(
        days: int = 14, student_id: str | None = None
    ) -> Any:
        sid = resolve_student(student_id)
        current = today(session().settings)
        start = iso(current)
        end = iso(current + timedelta(days=clamp(days, 1, 60)))
        data = await cached(
            f"timetable|{sid}|{start}|{end}",
            60.0,
            ep.get_timetable,
            sid,
            start,
            end,
        )
        changes = [
            course
            for course in timetable_items(data)
            if course.get("annule") or course.get("modifie")
        ]
        return {"from": start, "to": end, "count": len(changes), "changes": changes}
