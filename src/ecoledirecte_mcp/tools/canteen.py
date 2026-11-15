# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""School canteen (restauration) read tools."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..shaping import as_dict, as_list
from ..validation import require_date, require_numeric_id
from ._common import DOCUMENTS_TTL, cached, resolve_student


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_get_menus",
        description=(
            "Menus de la cantine, par semaine, avec l'identifiant du document "
            "à télécharger."
        ),
    )
    async def ed_get_menus(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(
            await cached(f"menus|{sid}", DOCUMENTS_TTL, ep.get_menus, sid)
        )

    @server.tool(
        name="ed_list_canteen_points",
        description=(
            "Points de passage de la cantine, créneaux et catégories d'articles "
            "(avec le détail des articles si include_articles=true)."
        ),
    )
    async def ed_list_canteen_points(
        include_articles: bool = False,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        data = as_dict(
            clean(
                await cached(
                    f"canteen|{sid}", DOCUMENTS_TTL, ep.get_canteen, sid
                )
            )
        )
        points = []
        for point in as_list(data.get("tabPointsDePassage")):
            if not isinstance(point, dict):
                continue
            if include_articles:
                points.append(point)
                continue
            categories = []
            for category in as_list(point.get("categoriesArticles")):
                if isinstance(category, dict):
                    categories.append(
                        {
                            "id": category.get("id"),
                            "libelle": category.get("libelle"),
                            "articles": len(as_list(category.get("articles"))),
                        }
                    )
            points.append(
                {
                    "id": point.get("id"),
                    "libelle": point.get("libelle"),
                    "plafond": point.get("plafond"),
                    "panierMinimum": point.get("panierMinimum"),
                    "creneaux": point.get("creneaux"),
                    "categories": categories,
                }
            )
        return {
            "pointsDePassage": points,
            "joursFeries": data.get("joursFeries"),
        }

    @server.tool(
        name="ed_list_canteen_orders",
        description=(
            "Historique des commandes de cantine : numéro, date, créneau, "
            "point de passage, état et articles."
        ),
    )
    async def ed_list_canteen_orders(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        data = as_dict(
            clean(
                await cached(
                    f"canteen|{sid}", DOCUMENTS_TTL, ep.get_canteen, sid
                )
            )
        )
        orders = [
            order
            for order in as_list(data.get("historiqueCommandes"))
            if isinstance(order, dict)
        ]
        return {"count": len(orders), "orders": orders}

    @server.tool(
        name="ed_check_canteen_slot",
        description=(
            "Vérifie un point de passage pour une date (AAAA-MM-JJ) : solde, "
            "plafonds, créneaux, articles disponibles et ruptures de stock."
        ),
    )
    async def ed_check_canteen_slot(
        point_id: str,
        date: str,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        point_id = require_numeric_id(point_id, "point_id")
        date = require_date(date, "date")
        return clean(
            await cached(
                f"canteen-slot|{sid}|{point_id}|{date}",
                60.0,
                ep.check_canteen_slot,
                sid,
                point_id,
                date,
            )
        )
