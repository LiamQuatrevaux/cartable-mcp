from ecoledirecte_mcp.shaping import (
    flatten_grades,
    message_summary,
    subjects,
    timetable_items,
)


def test_subjects_reads_disciplines() -> None:
    period = {
        "ensembleMatieres": {
            "disciplines": [
                {
                    "discipline": "MATHEMATIQUES",
                    "codeMatiere": "MATHS",
                    "moyenne": "16,5",
                }
            ]
        }
    }

    rows = subjects(period)

    assert len(rows) == 1
    assert rows[0]["discipline"] == "MATHEMATIQUES"


def test_flatten_grades_reads_top_level_notes() -> None:
    data = {
        "notes": [
            {
                "id": 1,
                "codeMatiere": "MATHS",
                "codeSousMatiere": "",
                "libelleMatiere": "MATHEMATIQUES",
                "codePeriode": "A001",
                "date": "2026-09-21",
                "devoir": "DS 1",
                "valeur": "16,5",
                "noteSur": "20",
                "coef": "1",
                "moyenneClasse": "13,5",
                "minClasse": "8",
                "maxClasse": "18",
            }
        ],
        "periodes": [],
    }

    rows = flatten_grades(data)

    assert len(rows) == 1
    assert rows[0]["matiere"] == "MATHEMATIQUES"
    assert rows[0]["note"] == "16,5"
    assert rows[0]["bareme"] == "20"
    assert rows[0]["min"] == "8"
    assert rows[0]["max"] == "18"
    assert rows[0]["codePeriode"] == "A001"


def test_timetable_items_unwraps_api_envelope() -> None:
    payload = {
        "code": 200,
        "data": [
            {
                "id": 89304,
                "matiere": "SECTION EUROPE",
                "prof": "BANSAL A.",
                "salle": "065 - 37 places",
                "start_date": "2026-11-16 09:10",
                "end_date": "2026-11-16 10:05",
                "isAnnule": False,
                "isModifie": False,
            }
        ],
    }

    rows = timetable_items(payload)

    assert len(rows) == 1
    assert rows[0]["matiere"] == "SECTION EUROPE"
    assert rows[0]["debut"] == "2026-11-16 09:10"
    assert rows[0]["annule"] is False


def test_message_summary_maps_ecole_directe_fields() -> None:
    summary = message_summary(
        {
            "id": 42,
            "date": "2026-11-10 18:18:56",
            "from": {"prenom": "J.", "nom": "LAUER"},
            "subject": "Collecte banque alimentaire",
            "read": True,
            "answered": False,
            "mtype": "received",
            "files": [{"id": 1}, {"id": 2}],
        }
    )

    assert summary["id"] == 42
    assert summary["de"] == "J. LAUER"
    assert summary["objet"] == "Collecte banque alimentaire"
    assert summary["lu"] is True
    assert summary["repondu"] is False
    assert summary["type"] == "received"
    assert summary["piecesJointes"] == 2
