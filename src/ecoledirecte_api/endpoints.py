# SPDX-FileCopyrightText: 2025 Giga77
# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Read-only endpoint helpers for the Ecole Directe API.

Every function takes an authenticated :class:`EDClient` as first argument so
the MCP layer controls concurrency, caching and login lifecycle.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ecoledirecte_api.client import DownloadedFile, EDClient
from ecoledirecte_api.exceptions import BaseEcoleDirecteException

Json = dict[str, Any]


def _body(data: Mapping[str, Any] | None = None) -> str:
    return "data=" + json.dumps(
        dict(data or {}), ensure_ascii=False, separators=(",", ":")
    )


def _query(
    client: EDClient, extra: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {"verbe": "get", "v": client.api_version}
    if extra:
        params.update(
            {key: value for key, value in extra.items() if value is not None}
        )
    return params


async def _get(
    client: EDClient,
    path: str,
    *,
    data: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
) -> Any:
    return await client.request(
        "POST", path, params=_query(client, params), payload=_body(data)
    )


# --- Élève / profil -------------------------------------------------------


async def get_student(client: EDClient, eleve_id: str) -> Any:
    """Profil de l'élève (route autorisée aux comptes élèves)."""
    return await _get(client, f"/eleves/{eleve_id}/details.awp")


async def get_timeline(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/eleves/{eleve_id}/timeline.awp")


async def get_common_timeline(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/E/{eleve_id}/timelineAccueilCommun.awp")


async def get_manuals(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/Eleves/{eleve_id}/manuelsNumeriques.awp")


async def get_visios(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/E/{eleve_id}/visios.awp")


async def get_qcms(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/eleves/{eleve_id}/qcms/0/associations.awp")


async def get_carnet(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/eleves/{eleve_id}/eleveCarnetCorrespondance.awp")


async def get_sessions_rdv(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/E/{eleve_id}/sessionsRdv.awp")


async def get_class_life(client: EDClient, classe_id: str) -> Json:
    """Fetch both known vie-de-classe routes; keep partial results."""
    result: Json = {}
    for key, path in (
        ("classes", f"/Classes/{classe_id}/viedelaclasse.awp"),
        ("r", f"/R/{classe_id}/viedelaclasse.awp"),
    ):
        try:
            result[key] = await _get(client, path)
        except BaseEcoleDirecteException as exc:
            result[key] = {"error": str(exc)}
    return result


async def get_class_students(client: EDClient, classe_id: str) -> Any:
    return await _get(client, f"/classes/{classe_id}/eleves.awp")


# --- Notes ----------------------------------------------------------------


async def get_notes(
    client: EDClient, eleve_id: str, annee_scolaire: str = ""
) -> Any:
    return await _get(
        client,
        f"/eleves/{eleve_id}/notes.awp",
        data={"anneeScolaire": annee_scolaire},
    )


# --- Cahier de textes -----------------------------------------------------


async def get_homework(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/Eleves/{eleve_id}/cahierdetexte.awp")


async def get_homework_day(client: EDClient, eleve_id: str, date: str) -> Any:
    return await _get(client, f"/Eleves/{eleve_id}/cahierdetexte/{date}.awp")


# --- Emploi du temps ------------------------------------------------------


async def get_timetable(
    client: EDClient, eleve_id: str, date_debut: str, date_fin: str
) -> Any:
    return await _get(
        client,
        f"/E/{eleve_id}/emploidutemps.awp",
        data={"dateDebut": date_debut, "dateFin": date_fin, "avecTrous": False},
    )


# --- Vie scolaire ---------------------------------------------------------


async def get_vie_scolaire(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/eleves/{eleve_id}/viescolaire.awp")


# --- Messagerie -----------------------------------------------------------


async def get_messages(
    client: EDClient,
    eleve_id: str,
    *,
    folder: str,
    annee: str,
    query: str = "",
    unread_only: bool = False,
    page: int = 0,
    per_page: int = 100,
    classeur_id: str = "0",
) -> Any:
    return await _get(
        client,
        f"/eleves/{eleve_id}/messages.awp",
        params={
            "force": "false",
            "typeRecuperation": folder,
            "idClasseur": classeur_id,
            "orderBy": "date",
            "order": "desc",
            "query": query,
            "onlyRead": "true" if unread_only else "",
            "page": str(page),
            "itemsPerPage": str(per_page),
            "getAll": "0",
        },
        data={"anneeMessages": annee},
    )


async def get_message(
    client: EDClient,
    eleve_id: str,
    message_id: str,
    *,
    mode: str,
    annee: str,
) -> Any:
    return await _get(
        client,
        f"/eleves/{eleve_id}/messages/{message_id}.awp",
        params={"mode": mode},
        data={"anneeMessages": annee},
    )


# --- Documents / comptes --------------------------------------------------


async def get_documents(client: EDClient, archive: str = "") -> Any:
    return await _get(client, "/elevesDocuments.awp", params={"archive": archive})


async def get_wallet_balances(client: EDClient) -> Any:
    return await _get(client, "/comptes/sansdetails.awp")


# --- Formulaires / sondages ----------------------------------------------


async def get_forms(client: EDClient, eleve_id: str, annee: str) -> Any:
    return await _get(
        client,
        "/edforms.awp",
        params={"verbe": "list"},
        data={"anneeForms": annee, "typeEntity": "E", "idEntity": int(eleve_id)},
    )


async def get_surveys(client: EDClient) -> Any:
    return await _get(client, "/rdt/sondages.awp")


# --- Restauration ---------------------------------------------------------


async def get_menus(client: EDClient, eleve_id: str) -> Any:
    return await _get(
        client, "/menusRestaurationScolaire.awp", data={"idEleve": int(eleve_id)}
    )


async def get_canteen(client: EDClient, eleve_id: str) -> Any:
    return await _get(client, f"/E/{eleve_id}/commandesPassage.awp")


async def check_canteen_slot(
    client: EDClient, eleve_id: str, pdp_id: str, date: str
) -> Any:
    compact = date.replace("-", "")
    return await _get(
        client,
        f"/E/{eleve_id}/commandesPassage/pointsDePassage/{pdp_id}/{compact}.awp",
    )


# --- Espaces de travail / cloud ------------------------------------------


async def get_workspaces(
    client: EDClient, eleve_id: str, account_type: str = "E"
) -> Any:
    return await _get(
        client,
        f"/{account_type}/{eleve_id}/espacestravail.awp",
        params={"typeModule": "espaceTravail"},
    )


async def get_workspace(
    client: EDClient, espace_id: str, eleve_id: str, account_type: str = "E"
) -> Any:
    return await _get(
        client, f"/{account_type}/{eleve_id}/espacestravail/{espace_id}.awp"
    )


async def get_workspace_activities(
    client: EDClient, espace_id: str, eleve_id: str, account_type: str = "E"
) -> Any:
    return await _get(
        client,
        f"/{account_type}/{eleve_id}/espacestravail/{espace_id}/activites.awp",
    )


async def get_workspace_activity(
    client: EDClient,
    espace_id: str,
    eleve_id: str,
    activity_id: str,
    account_type: str = "E",
) -> Any:
    return await _get(
        client,
        f"/{account_type}/{eleve_id}/espacestravail/{espace_id}"
        f"/{activity_id}/cloudactivites.awp",
    )


async def get_postits(client: EDClient, espace_id: str) -> Any:
    return await _get(client, f"/W/{espace_id}/postits.awp")


async def get_cloud(
    client: EDClient,
    eleve_id: str,
    *,
    folder: str | None = None,
    workspace_id: str | None = None,
) -> Any:
    if workspace_id is not None:
        path = f"/cloud/W/{workspace_id}.awp"
    else:
        path = f"/cloud/E/{eleve_id}.awp"
    return await _get(client, path, params={"idfolder": folder})


# --- Téléchargement -------------------------------------------------------


async def download(
    client: EDClient,
    file_id: str,
    file_type: str | None = None,
    *,
    extra: Mapping[str, Any] | None = None,
    max_bytes: int | None = None,
) -> DownloadedFile:
    return await client.download_bytes(
        file_id, file_type, extra_params=extra, max_bytes=max_bytes
    )
