# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Cahier de textes tools."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..shaping import as_dict, homework_items, iso, today
from ..validation import require_date, require_range
from ._common import cached, resolve_student, session


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_list_homework",
        description=(
            "Travail à faire, groupé par date (idDevoir, matière, effectué, "
            "interrogation, documents). Par défaut : aujourd'hui + 7 jours."
        ),
    )
    async def ed_list_homework(
        date_debut: str | None = None,
        date_fin: str | None = None,
        only_pending: bool = False,
        student_id: str | None = None,
    ) -> Any:
        sid = resolve_student(student_id)
        current = today(session().settings)
        start = date_debut or iso(current)
        end = date_fin or iso(current + timedelta(days=7))
        start, end = require_range(start, end)
        data = clean(await cached(f"homework|{sid}", 120.0, ep.get_homework, sid))

        rows = [
            item
            for item in homework_items(data)
            if start <= str(item.get("date") or "") <= end
            and (not only_pending or not item.get("effectue"))
        ]
        by_day: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_day.setdefault(str(row["date"]), []).append(row)
        return {
            "from": start,
            "to": end,
            "count": len(rows),
            "pending": sum(1 for row in rows if not row.get("effectue")),
            "days": [{"date": day, "items": items} for day, items in by_day.items()],
        }

    @server.tool(
        name="ed_get_homework_day",
        description=(
            "Détail complet d'une journée de cahier de textes : contenu du "
            "travail à faire, contenu de séance, pièces jointes, commentaires et "
            "documents rendus (textes base64/HTML décodés)."
        ),
    )
    async def ed_get_homework_day(
        date: str,
        student_id: str | None = None,
    ) -> Any:
        sid = resolve_student(student_id)
        day = require_date(date, "date")
        return clean(
            await cached(
                f"homework-day|{sid}|{day}",
                300.0,
                ep.get_homework_day,
                sid,
                day,
            )
        )

    @server.tool(
        name="ed_list_homework_subjects",
        description=(
            "Vue synthétique par matière du travail à faire (nombre de devoirs, "
            "devoirs non faits, prochaine échéance)."
        ),
    )
    async def ed_list_homework_subjects(
        student_id: str | None = None,
    ) -> Any:
        sid = resolve_student(student_id)
        data = clean(await cached(f"homework|{sid}", 120.0, ep.get_homework, sid))
        grouped: dict[str, dict[str, Any]] = {}
        for item in homework_items(data):
            subject = str(item.get("matiere") or "—")
            entry = grouped.setdefault(
                subject,
                {
                    "matiere": subject,
                    "codeMatiere": item.get("codeMatiere"),
                    "total": 0,
                    "pending": 0,
                    "next": None,
                },
            )
            entry["total"] += 1
            if not item.get("effectue"):
                entry["pending"] += 1
                if entry["next"] is None or str(item.get("date")) < str(entry["next"]):
                    entry["next"] = item.get("date")
        rows = sorted(grouped.values(), key=lambda row: str(row["matiere"]))
        return {"count": len(rows), "subjects": rows}

    @server.tool(
        name="ed_get_homework_index",
        description=(
            "Index brut du cahier de textes par date, sans filtrage : utile pour "
            "savoir quelles journées contiennent des devoirs."
        ),
    )
    async def ed_get_homework_index(
        student_id: str | None = None,
    ) -> Any:
        sid = resolve_student(student_id)
        data = clean(await cached(f"homework|{sid}", 120.0, ep.get_homework, sid))
        payload = as_dict(data)
        return {
            "days": sorted(payload.keys()),
            "count": sum(len(items) for items in payload.values() if isinstance(items, list)),
        }
