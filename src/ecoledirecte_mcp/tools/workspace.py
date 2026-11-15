# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Workspaces and student cloud read tools."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean

from ..validation import require_numeric_id, require_remote_path
from ._common import (
    WORKSPACE_TTL,
    basename_of,
    cached,
    resolve_student,
    session,
    store,
)


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_list_workspaces",
        description=(
            "Espaces de travail de l'élève : titre, résumé, nombre de membres, "
            "droits et fonctionnalités (cloud, discussion, agenda)."
        ),
    )
    async def ed_list_workspaces(student_id: str | None = None) -> Any:
        sid = await resolve_student(student_id)
        return clean(
            await cached(
                f"workspaces|{sid}", WORKSPACE_TTL, ep.get_workspaces, sid
            )
        )

    @server.tool(
        name="ed_get_workspace",
        description="Détail d'un espace de travail (membres, description, options).",
    )
    async def ed_get_workspace(
        espace_id: str, student_id: str | None = None
    ) -> Any:
        sid = await resolve_student(student_id)
        espace_id = require_numeric_id(espace_id, "espace_id")
        return clean(
            await cached(
                f"workspace|{sid}|{espace_id}",
                WORKSPACE_TTL,
                ep.get_workspace,
                espace_id,
                sid,
            )
        )

    @server.tool(
        name="ed_list_workspace_activities",
        description="Activités publiées dans un espace de travail.",
    )
    async def ed_list_workspace_activities(
        espace_id: str, student_id: str | None = None
    ) -> Any:
        sid = await resolve_student(student_id)
        espace_id = require_numeric_id(espace_id, "espace_id")
        return clean(
            await cached(
                f"workspace-activities|{sid}|{espace_id}",
                WORKSPACE_TTL,
                ep.get_workspace_activities,
                espace_id,
                sid,
            )
        )

    @server.tool(
        name="ed_get_workspace_activity",
        description="Détail d'une activité cloud d'un espace de travail.",
    )
    async def ed_get_workspace_activity(
        espace_id: str,
        activity_id: str,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        espace_id = require_numeric_id(espace_id, "espace_id")
        activity_id = require_numeric_id(activity_id, "activity_id")
        return clean(
            await cached(
                f"workspace-activity|{sid}|{espace_id}|{activity_id}",
                WORKSPACE_TTL,
                ep.get_workspace_activity,
                espace_id,
                sid,
                activity_id,
            )
        )

    @server.tool(
        name="ed_list_workspace_postits",
        description="Post-its d'un espace de travail (contenu décodé).",
    )
    async def ed_list_workspace_postits(espace_id: str) -> Any:
        return clean(
            await cached(
                f"postits|{espace_id}", WORKSPACE_TTL, ep.get_postits, espace_id
            )
        )

    @server.tool(
        name="ed_list_cloud",
        description=(
            "Contenu du cloud de l'élève (ou d'un espace de travail) : dossiers "
            "et fichiers avec taille, date et chemin UNC. Sans folder, renvoie "
            "la racine."
        ),
    )
    async def ed_list_cloud(
        folder: str | None = None,
        workspace_id: str | None = None,
        student_id: str | None = None,
    ) -> Any:
        sid = await resolve_student(student_id)
        if folder is not None:
            folder = require_remote_path(folder, "folder")
        if workspace_id is not None:
            workspace_id = require_numeric_id(workspace_id, "workspace_id")
        return clean(
            await session().fetch(
                f"cloud|{sid}|{workspace_id or ''}|{folder or ''}",
                WORKSPACE_TTL,
                ep.get_cloud,
                sid,
                folder=folder,
                workspace_id=workspace_id,
            )
        )

    @server.tool(
        name="ed_download_cloud_file",
        description=(
            "Télécharge un fichier du cloud à partir de son chemin UNC (champ "
            "'id' renvoyé par ed_list_cloud)."
        ),
    )
    async def ed_download_cloud_file(unc_path: str) -> Any:
        settings = session().settings
        unc_path = require_remote_path(unc_path, "unc_path")
        file = await session().run(
            ep.download,
            unc_path,
            "CLOUD",
            max_bytes=settings.max_download_bytes,
        )
        return store(file, basename_of(unc_path))
