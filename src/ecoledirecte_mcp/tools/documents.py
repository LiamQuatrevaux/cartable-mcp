# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Official documents, wallet, forms and surveys."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..shaping import as_list
from ..validation import require_numeric_id, require_token_id, require_year
from ._common import (
    DOCUMENTS_TTL,
    cached,
    resolve_student,
    school_year,
    session,
    store,
)


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_list_documents",
        description=(
            "Documents officiels de l'élève : bulletins, attestations, "
            "documents administratifs, vie scolaire, factures et inscriptions. "
            "Par défaut l'année en cours, sinon passer annee=AAAA-AAAA."
        ),
    )
    async def ed_list_documents(
        annee: str | None = None, student_id: str | None = None
    ) -> Any:
        del student_id
        archive = require_year(annee) or ""
        return clean(
            await cached(
                f"documents|{archive}",
                DOCUMENTS_TTL,
                ep.get_documents,
                archive,
            )
        )

    @server.tool(
        name="ed_list_pieces_a_verser",
        description=(
            "Pièces justificatives à fournir à l'établissement, avec les "
            "personnes concernées et les téléversements déjà effectués."
        ),
    )
    async def ed_list_pieces_a_verser(
        annee: str | None = None, student_id: str | None = None
    ) -> Any:
        del student_id
        archive = require_year(annee) or ""
        data = clean(
            await cached(
                f"documents|{archive}",
                DOCUMENTS_TTL,
                ep.get_documents,
                archive,
            )
        )
        if isinstance(data, dict):
            return data.get("listesPiecesAVerser") or {}
        return {}

    @server.tool(
        name="ed_get_wallet_balances",
        description=(
            "Soldes des comptes de restauration / portefeuille de l'élève."
        ),
    )
    async def ed_get_wallet_balances() -> Any:
        return clean(
            await cached(
                "wallet", DOCUMENTS_TTL, ep.get_wallet_balances
            )
        )

    @server.tool(
        name="ed_download_document",
        description=(
            "Télécharge un document officiel (bulletins, attestations, "
            "justificatifs) et renvoie son chemin local."
        ),
    )
    async def ed_download_document(file_id: str, annee: str | None = None) -> Any:
        settings = session().settings
        file_id = require_token_id(file_id, "file_id")
        annee = require_year(annee, "annee")
        extra = {"archive": "true", "anneeArchive": annee} if annee else None
        file = await session().run(
            ep.download,
            file_id,
            None,
            extra=extra,
            max_bytes=settings.max_download_bytes,
        )
        return store(file, f"document-{file_id}")

    @server.tool(
        name="ed_list_forms",
        description=(
            "Formulaires Ecole Directe de l'année : titre, état, échéance, "
            "questions et propositions (base64 décodé)."
        ),
    )
    async def ed_list_forms(
        annee: str | None = None, student_id: str | None = None
    ) -> Any:
        sid = await resolve_student(student_id)
        year = school_year(annee)
        data = clean(
            await cached(
                f"forms|{sid}|{year}",
                DOCUMENTS_TTL,
                ep.get_forms,
                sid,
                year,
            )
        )
        return {"annee": year, "forms": data}

    @server.tool(
        name="ed_get_form",
        description=(
            "Détail d'un formulaire par son identifiant, avec les questions "
            "décodées et l'état de complétion."
        ),
    )
    async def ed_get_form(
        form_id: str,
        annee: str | None = None,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        year = school_year(annee)
        form_id = require_numeric_id(form_id, "form_id")
        data = clean(
            await cached(
                f"forms|{sid}|{year}",
                DOCUMENTS_TTL,
                ep.get_forms,
                sid,
                year,
            )
        )
        needle = str(form_id)
        for form in as_list(data):
            if not isinstance(form, dict):
                continue
            formulaire = form.get("formulaire")
            identifiant = (
                formulaire.get("id") if isinstance(formulaire, dict) else None
            )
            if str(identifiant) == needle or str(form.get("id")) == needle:
                return form
        return {"error": f"Formulaire {form_id} introuvable.", "forms": data}

    @server.tool(
        name="ed_list_surveys",
        description="Sondages et questionnaires disponibles pour l'élève.",
    )
    async def ed_list_surveys() -> Any:
        return clean(
            await cached("surveys", DOCUMENTS_TTL, ep.get_surveys)
        )
