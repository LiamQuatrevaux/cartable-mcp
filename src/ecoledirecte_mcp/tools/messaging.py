# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Read-only mailbox tools."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..shaping import as_dict, as_list, message_summary
from ..validation import (
    clamp,
    require_choice,
    require_text,
    require_token_id,
    require_year,
)
from ._common import MESSAGES_TTL, cached, resolve_student, school_year, session, store

_FOLDERS = {"received", "sent", "archived", "draft"}


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_list_messages",
        description=(
            "Liste les messages d'un dossier (received, sent, archived, draft) "
            "avec objet, expéditeur, date, statut lu et nombre de pièces jointes."
        ),
    )
    async def ed_list_messages(
        folder: str = "received",
        annee: str | None = None,
        query: str = "",
        unread_only: bool = False,
        page: int = 0,
        per_page: int = 100,
        preview: int = 0,
        student_id: str | None = None,
    ) -> Any:
        folder = require_choice(folder, "folder", _FOLDERS)
        page = clamp(page, 0, 10_000)
        per_page = clamp(per_page, 1, 200)
        preview = clamp(preview, 0, 1_000)
        query = require_text(query, "query", 200)
        sid = resolve_student(student_id)
        year = school_year(annee)
        payload = clean(
            await cached(
                f"messages|{sid}|{folder}|{year}|{query}|{unread_only}|{page}|{per_page}",
                MESSAGES_TTL,
                ep.get_messages,
                sid,
                folder=folder,
                annee=year,
                query=query,
                unread_only=unread_only,
                page=page,
                per_page=per_page,
            )
        )
        payload_dict = as_dict(payload)
        container = payload_dict.get("messages")
        if isinstance(container, dict):
            raw = container.get(folder)
        elif isinstance(container, list):
            raw = container
        else:
            raw = None
        messages = [
            message_summary(message, preview=preview)
            for message in as_list(raw)
            if isinstance(message, dict)
        ]
        counts = as_dict(payload_dict.get("pagination"))
        count_key = {
            "received": "messagesRecusCount",
            "sent": "messagesEnvoyesCount",
            "archived": "messagesArchivesCount",
            "draft": "messagesDraftCount",
        }.get(folder, "")
        total = counts.get(count_key) if count_key else None
        if not isinstance(total, int):
            total = len(messages)
        return {
            "folder": folder,
            "annee": year,
            "total": total,
            "page": page,
            "messages": messages,
        }

    @server.tool(
        name="ed_get_message",
        description=(
            "Message complet : corps décodé (HTML → texte), expéditeur, "
            "destinataires, pièces jointes. Ouvrir un message le marque comme lu "
            "côté Ecole Directe, comme sur le site."
        ),
    )
    async def ed_get_message(
        message_id: str,
        folder: str = "received",
        annee: str | None = None,
        mode: str = "destinataire",
        student_id: str | None = None,
    ) -> Any:
        del folder  # le détail n'utilise pas le dossier, seulement l'année
        message_id = require_token_id(message_id, "message_id")
        mode = require_choice(mode, "mode", {"destinataire", "expediteur"})
        sid = resolve_student(student_id)
        return clean(
            await session().run(
                ep.get_message,
                sid,
                message_id,
                mode=mode,
                annee=school_year(annee),
            )
        )

    @server.tool(
        name="ed_download_message_attachment",
        description=(
            "Télécharge une pièce jointe de message dans le dossier de "
            "téléchargement et renvoie son chemin local."
        ),
    )
    async def ed_download_message_attachment(
        file_id: str, annee: str | None = None
    ) -> Any:
        settings = session().settings
        file_id = require_token_id(file_id, "file_id")
        annee = require_year(annee, "annee")
        extra = {"anneeMessages": annee} if annee else None
        file = await session().run(
            ep.download,
            file_id,
            "PIECE_JOINTE",
            extra=extra,
            max_bytes=settings.max_download_bytes,
        )
        return store(file, f"piece-jointe-{file_id}")
