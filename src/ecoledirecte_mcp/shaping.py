# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Small normalizers that turn raw ED payloads into compact agent context."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ecoledirecte_api.codec import data_of

from .config import Settings


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def today(settings: Settings) -> date:
    """Current date in the configured timezone."""
    try:
        tz = ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = None
    return datetime.now(tz).date()


def iso(value: date) -> str:
    return value.isoformat()


def periods(data: Any) -> list[dict[str, Any]]:
    """Return the note periods of a ``notes.awp`` payload."""
    return [p for p in as_list(as_dict(data).get("periodes")) if isinstance(p, dict)]


def subjects(period: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the subject rows of a period."""
    ensemble = as_dict(period.get("ensembleMatieres"))
    raw = ensemble.get("disciplines")
    if not isinstance(raw, list):
        raw = ensemble.get("matieres")
    return [m for m in as_list(raw) if isinstance(m, dict)]


def find_period(data: Any, reference: str) -> dict[str, Any] | None:
    """Find a period by code, id or label (case-insensitive)."""
    needle = reference.strip().lower()
    for period in periods(data):
        candidates = {
            str(period.get("codePeriode") or "").lower(),
            str(period.get("idPeriode") or "").lower(),
            str(period.get("periode") or "").lower(),
        }
        if needle in candidates:
            return period
    return None


def period_summary(period: Mapping[str, Any]) -> dict[str, Any]:
    ensemble = as_dict(period.get("ensembleMatieres"))
    return {
        "codePeriode": period.get("codePeriode") or period.get("idPeriode"),
        "periode": period.get("periode"),
        "annuel": period.get("annuel"),
        "dateDebut": period.get("dateDebut"),
        "dateFin": period.get("dateFin"),
        "cloture": period.get("cloture"),
        "moyenne": ensemble.get("moyenneGenerale"),
        "moyenneClasse": ensemble.get("moyenneClasse"),
        "moyenneMin": ensemble.get("moyenneMin"),
        "moyenneMax": ensemble.get("moyenneMax"),
        "rang": ensemble.get("rang") or ensemble.get("moyenneRang"),
        "appreciation": ensemble.get("appreciation"),
        "professeurs": ensemble.get("professeurs"),
    }


def flatten_grades(data: Any) -> list[dict[str, Any]]:
    """Flatten every grade of every period into one list (newest first)."""
    payload = as_dict(data)
    rows: list[dict[str, Any]] = []
    flat_notes = payload.get("notes")
    if isinstance(flat_notes, list):
        for note in flat_notes:
            if not isinstance(note, dict):
                continue
            rows.append(
                {
                    "periode": note.get("periode") or note.get("codePeriode"),
                    "codePeriode": note.get("codePeriode") or note.get("idPeriode"),
                    "matiere": note.get("libelleMatiere") or note.get("matiere"),
                    "codeMatiere": note.get("codeMatiere"),
                    "codeSousMatiere": note.get("codeSousMatiere") or "",
                    "id": note.get("id"),
                    "date": note.get("date") or note.get("dateSaisie"),
                    "devoir": note.get("devoir"),
                    "note": note.get("valeur"),
                    "bareme": note.get("noteSur") or note.get("bareme"),
                    "coef": note.get("coef"),
                    "moyenneClasse": note.get("moyenneClasse"),
                    "min": note.get("minClasse", note.get("min")),
                    "max": note.get("maxClasse", note.get("max")),
                    "appreciation": note.get("commentaire")
                    or note.get("appreciation"),
                    "typeDevoir": note.get("typeDevoir"),
                    "absent": note.get("absent"),
                    "nonNote": note.get("nonNote"),
                    "nonSignificatif": note.get("nonSignificatif"),
                }
            )
    else:
        for period in periods(data):
            for subject in subjects(period):
                for note in as_list(subject.get("notes")):
                    if not isinstance(note, dict):
                        continue
                    rows.append(
                        {
                            "periode": period.get("periode"),
                            "codePeriode": period.get("codePeriode")
                            or period.get("idPeriode"),
                            "matiere": subject.get("matiere")
                            or subject.get("discipline"),
                            "codeMatiere": subject.get("codeMatiere"),
                            "codeSousMatiere": subject.get("codeSousMatiere") or "",
                            "id": note.get("id"),
                            "date": note.get("date") or note.get("dateSaisie"),
                            "devoir": note.get("devoir"),
                            "note": note.get("valeur"),
                            "bareme": note.get("bareme") or note.get("noteSur"),
                            "coef": note.get("coef"),
                            "moyenneClasse": note.get("moyenneClasse"),
                            "min": note.get("min", note.get("minClasse")),
                            "max": note.get("max", note.get("maxClasse")),
                            "appreciation": note.get("appreciation")
                            or note.get("commentaire"),
                            "typeDevoir": note.get("typeDevoir"),
                            "absent": note.get("absent"),
                            "nonNote": note.get("nonNote"),
                            "nonSignificatif": note.get("nonSignificatif"),
                        }
                    )
    rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    return rows


def attendance(data: Any) -> dict[str, Any]:
    """Split ``absencesRetards`` into absences and retards."""
    payload = as_dict(data)
    absences: list[dict[str, Any]] = []
    retards: list[dict[str, Any]] = []
    for item in as_list(payload.get("absencesRetards")):
        if not isinstance(item, dict):
            continue
        kind = " ".join(
            str(item.get(key) or "") for key in ("type", "typeElement", "libelle")
        ).lower()
        (retards if "retard" in kind else absences).append(item)
    return {
        "absences": absences,
        "retards": retards,
        "sanctions": [i for i in as_list(payload.get("sanctions")) if isinstance(i, dict)],
        "encouragements": [
            i for i in as_list(payload.get("encouragements")) if isinstance(i, dict)
        ],
        "dispenses": [
            i for i in as_list(payload.get("dispenses")) if isinstance(i, dict)
        ],
        "parametres": payload.get("parametres"),
    }


def message_summary(message: Mapping[str, Any], preview: int = 0) -> dict[str, Any]:
    """Compact representation of one mailbox row."""
    attachments = message.get("files") or message.get("piecesJointes")
    sender = message.get("from") or message.get("de")
    if isinstance(sender, Mapping):
        sender = " ".join(
            str(sender.get(key) or "").strip()
            for key in ("prenom", "nom")
        ).strip()
    summary: dict[str, Any] = {
        "id": message.get("id"),
        "date": message.get("date"),
        "de": sender,
        "objet": message.get("subject") or message.get("objet"),
        "lu": message.get("read", message.get("lu")),
        "repondu": message.get("answered", message.get("repondu")),
        "type": message.get("mtype") or message.get("type"),
        "piecesJointes": len(as_list(attachments)),
    }
    if preview:
        content = message.get("contenu") or message.get("content")
        if isinstance(content, str) and content:
            text = " ".join(content.split())
            summary["apercu"] = (
                text if len(text) <= preview else text[: preview - 1] + "…"
            )
    return summary


def homework_items(data: Any) -> list[dict[str, Any]]:
    """Flatten the date-keyed cahier de textes payload."""
    rows: list[dict[str, Any]] = []
    for day, items in as_dict(data).items():
        for item in as_list(items):
            if isinstance(item, dict):
                rows.append(
                    {
                        "date": day,
                        "idDevoir": item.get("idDevoir") or item.get("id"),
                        "matiere": item.get("matiere"),
                        "codeMatiere": item.get("codeMatiere"),
                        "aFaire": item.get("aFaire"),
                        "effectue": item.get("effectue"),
                        "donneLe": item.get("donneLe"),
                        "interrogation": item.get("interrogation"),
                        "documentsAFaire": item.get("documentsAFaire"),
                    }
                )
    rows.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("matiere"))))
    return rows


def timetable_items(data: Any) -> list[dict[str, Any]]:
    """Normalize timetable events to a stable shape."""
    rows: list[dict[str, Any]] = []
    for item in as_list(data_of(data)):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": item.get("id"),
                "matiere": item.get("matiere") or item.get("text"),
                "prof": item.get("prof"),
                "salle": item.get("salle"),
                "debut": item.get("start_date") or item.get("startDate"),
                "fin": item.get("end_date") or item.get("endDate"),
                "typeCours": item.get("typeCours"),
                "annule": item.get("isAnnule"),
                "modifie": item.get("isModifie"),
                "dispense": item.get("dispense"),
                "classe": item.get("classe"),
                "groupe": item.get("groupe"),
            }
        )
    rows.sort(key=lambda row: str(row.get("debut") or ""))
    return rows
