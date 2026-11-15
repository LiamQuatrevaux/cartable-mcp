# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Grades, averages, appreciations and competencies."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..shaping import (
    find_period,
    flatten_grades,
    period_summary,
    periods,
    subjects,
)
from ._common import NOTES_TTL, cached, resolve_student, school_year


async def _notes(sid: str, annee: str) -> Any:
    return clean(
        await cached(f"notes|{sid}|{annee}", NOTES_TTL, ep.get_notes, sid, annee)
    )


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_list_periods",
        description=(
            "Liste les périodes de notation (trimestres + année) avec dates, "
            "clôture, moyenne générale, moyenne de classe, min/max et rang."
        ),
    )
    async def ed_list_periods(
        annee: str | None = None, student_id: str | None = None
    ) -> Any:
        sid = await resolve_student(student_id)
        data = await _notes(sid, school_year(annee))
        return [period_summary(period) for period in periods(data)]

    @server.tool(
        name="ed_get_period_report",
        description=(
            "Bulletin d'une période : moyennes, appréciation générale et détail "
            "par matière (moyenne, moyenne de classe, min/max, appréciation, "
            "notes). Si period est omise, prend la période en cours."
        ),
    )
    async def ed_get_period_report(
        period: str | None = None,
        annee: str | None = None,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        data = await _notes(sid, school_year(annee))
        available = periods(data)
        if not available:
            return {"periods": [], "message": "Aucune période de notation."}

        selected: dict[str, Any] | None
        if period:
            selected = find_period(data, period)
            if selected is None:
                return {
                    "error": f"Période inconnue : {period}",
                    "available": [period_summary(p) for p in available],
                }
        else:
            selected = next(
                (p for p in available if not p.get("annuel")), available[0]
            )

        selected_code = str(
            selected.get("codePeriode") or selected.get("idPeriode") or ""
        )
        all_notes = [
            note
            for note in flatten_grades(data)
            if str(note.get("codePeriode") or "") == selected_code
        ]
        rows: list[dict[str, Any]] = []
        for subject in subjects(selected):
            code = str(subject.get("codeMatiere") or "")
            sub_code = str(subject.get("codeSousMatiere") or "")
            subject_notes = [
                note
                for note in all_notes
                if str(note.get("codeMatiere") or "") == code
                and (
                    not sub_code
                    or str(note.get("codeSousMatiere") or "") == sub_code
                )
            ]
            rows.append(
                {
                    "matiere": subject.get("matiere") or subject.get("discipline"),
                    "codeMatiere": subject.get("codeMatiere"),
                    "codeSousMatiere": subject.get("codeSousMatiere") or "",
                    "professeurs": subject.get("professeurs"),
                    "moyenne": subject.get("moyenne"),
                    "moyenneClasse": subject.get("moyenneClasse"),
                    "moyenneMin": subject.get("moyenneMin"),
                    "moyenneMax": subject.get("moyenneMax"),
                    "appreciation": subject.get("appreciation"),
                    "notes": subject_notes,
                }
            )
        return {"period": period_summary(selected), "subjects": rows}

    @server.tool(
        name="ed_list_subject_grades",
        description=(
            "Toutes les notes individuelles (triées de la plus récente à la plus "
            "ancienne), filtrables par période et par matière."
        ),
    )
    async def ed_list_subject_grades(
        period: str | None = None,
        subject: str | None = None,
        limit: int = 200,
        annee: str | None = None,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        data = await _notes(sid, school_year(annee))
        rows = flatten_grades(data)
        if period:
            needle = period.strip().lower()
            rows = [
                row
                for row in rows
                if needle
                in {
                    str(row.get("codePeriode") or "").lower(),
                    str(row.get("periode") or "").lower(),
                }
            ]
        if subject:
            needle = subject.strip().lower()
            rows = [
                row
                for row in rows
                if needle
                in {
                    str(row.get("matiere") or "").lower(),
                    str(row.get("codeMatiere") or "").lower(),
                }
            ]
        return {"count": len(rows), "grades": rows[: max(1, limit)]}

    @server.tool(
        name="ed_list_evaluations",
        description=(
            "Évaluations récentes : notes avec leur type de devoir et les "
            "appréciations, les plus récentes d'abord."
        ),
    )
    async def ed_list_evaluations(
        limit: int = 30,
        annee: str | None = None,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        data = await _notes(sid, school_year(annee))
        rows = flatten_grades(data)
        return {"count": len(rows), "evaluations": rows[: max(1, limit)]}

    @server.tool(
        name="ed_list_competences",
        description=(
            "Compétences et éléments du programme (LSU) renseignés par les "
            "professeurs, par matière et par période."
        ),
    )
    async def ed_list_competences(
        period: str | None = None,
        annee: str | None = None,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        data = await _notes(sid, school_year(annee))
        selected_periods = periods(data)
        if period:
            selected = find_period(data, period)
            selected_periods = [selected] if selected else []

        rows: list[dict[str, Any]] = []
        for current in selected_periods:
            for subject in subjects(current):
                competences = subject.get("competences")
                elements = subject.get("elementsProg")
                if not competences and not elements:
                    continue
                rows.append(
                    {
                        "periode": current.get("periode"),
                        "matiere": subject.get("matiere"),
                        "competences": competences,
                        "elementsProg": elements,
                    }
                )
        return {
            "count": len(rows),
            "competences": rows,
            "message": None
            if rows
            else "Aucune compétence renseignée (LSU non activé pour cet établissement).",
        }

    @server.tool(
        name="ed_get_annual_summary",
        description=(
            "Synthèse annuelle : moyenne générale de l'année et moyennes de "
            "chaque période, avec leur appréciation."
        ),
    )
    async def ed_get_annual_summary(
        annee: str | None = None, student_id: str | None = None
    ) -> Any:
        sid = await resolve_student(student_id)
        data = await _notes(sid, school_year(annee))
        summaries = [period_summary(period) for period in periods(data)]
        annual = next(
            (item for item in summaries if item.get("annuel")),
            None,
        )
        return {"annual": annual, "periods": summaries}
