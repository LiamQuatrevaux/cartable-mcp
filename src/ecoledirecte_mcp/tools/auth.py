# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Authentication and global context tools."""

from __future__ import annotations

import time
from typing import Any

from aiohttp import ClientError
from mcp.server.mcpserver import MCPServer

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.codec import clean
from ecoledirecte_api.exceptions import (
    BaseEcoleDirecteException,
    QCMChallengeRequired,
)

from ..runtime import get_session
from ..session import AuthRequired, SessionLimitError
from ._common import challenge_response, resolve_student


def register(server: MCPServer) -> None:
    @server.tool(
        name="ed_auth_status",
        description=(
            "État de la session Ecole Directe : identifiants configurés, "
            "connexion active, comptes/élèves disponibles, QCM en attente, cache. "
            "Aucun appel réseau."
        ),
    )
    async def ed_auth_status() -> dict[str, Any]:
        return get_session().status()

    @server.tool(
        name="ed_login",
        description=(
            "Ouvre la session Ecole Directe. Si le serveur demande un QCM de "
            "vérification, renvoie status=qcm_required avec la question et ses "
            "propositions : demander la réponse à l'utilisateur puis appeler "
            "ed_submit_qcm."
        ),
    )
    async def ed_login() -> dict[str, Any]:
        session = get_session()
        try:
            return {"status": "authenticated", **await session.login()}
        except QCMChallengeRequired as exc:
            return challenge_response(exc)
        except SessionLimitError as exc:
            return {
                "status": "session_limit",
                "message": str(exc),
                "hint": "Attends quelques minutes, puis réutilise ed_get_context "
                "au lieu de rappeler ed_login.",
            }
        except AuthRequired as exc:
            return {"status": "not_configured", "message": str(exc)}

    @server.tool(
        name="ed_submit_qcm",
        description=(
            "Répond au QCM de connexion Ecole Directe. 'answer' doit être "
            "exactement l'une des propositions renvoyées par ed_login. "
            "La réponse est mémorisée pour les prochaines connexions."
        ),
    )
    async def ed_submit_qcm(answer: str) -> dict[str, Any]:
        session = get_session()
        try:
            return {"status": "authenticated", **await session.submit_qcm(answer)}
        except QCMChallengeRequired as exc:
            return challenge_response(exc)
        except (BaseEcoleDirecteException, ClientError, ValueError) as exc:
            return {
                "status": "failed",
                "message": str(exc),
                "hint": "La réponse est probablement incorrecte : "
                "appelle ed_login pour obtenir une nouvelle question.",
            }

    @server.tool(
        name="ed_logout",
        description="Ferme la session HTTP Ecole Directe (les identifiants sont conservés).",
    )
    async def ed_logout() -> dict[str, Any]:
        await get_session().logout()
        return {"status": "logged_out"}

    @server.tool(
        name="ed_select_account",
        description=(
            "Bascule la session sur un autre compte du même identifiant "
            "(utile si plusieurs établissements). Les comptes sont listés par "
            "ed_auth_status."
        ),
    )
    async def ed_select_account(id_login: int) -> dict[str, Any]:
        return await get_session().select_account(id_login)

    @server.tool(
        name="ed_get_context",
        description=(
            "Contexte complet pour démarrer : identité de l'élève, classe, "
            "établissement, année scolaire, modules Ecole Directe activés et "
            "liste des élèves du compte. À appeler une fois au début d'une "
            "conversation."
        ),
    )
    async def ed_get_context() -> dict[str, Any]:
        session = get_session()
        try:
            await session.client()
        except AuthRequired as exc:
            return {"status": "not_configured", "message": str(exc)}
        except QCMChallengeRequired as exc:
            return challenge_response(exc)
        except SessionLimitError as exc:
            return {
                "status": "session_limit",
                "message": str(exc),
                "hint": "Attends quelques minutes avant de réessayer.",
            }
        sid = resolve_student(None)
        try:
            profile = clean(
                await session.fetch(f"profile|{sid}", 600.0, ep.get_student, sid)
            )
        except QCMChallengeRequired as exc:
            return challenge_response(exc)

        modules: list[dict[str, Any]] = []
        for account in session.accounts:
            candidates: list[dict[str, Any]] = [account]
            children = account.get("eleves")
            if isinstance(children, list):
                candidates.extend(c for c in children if isinstance(c, dict))
            for candidate in candidates:
                if str(candidate.get("id")) != sid:
                    continue
                for module in candidate.get("modules") or []:
                    if isinstance(module, dict):
                        modules.append(
                            {
                                "code": module.get("code"),
                                "enable": module.get("enable"),
                                "badge": module.get("badge"),
                            }
                        )

        return {
            "read_only": True,
            "student_id": sid,
            "annee_scolaire": session.default_year(),
            "students": session.students,
            "accounts": session.status()["accounts"],
            "modules": modules,
            "profile": profile,
        }

    @server.tool(
        name="ed_health",
        description=(
            "Vérifie la session. Avec probe=true, effectue un appel réel léger "
            "et renvoie la latence de l'API Ecole Directe."
        ),
    )
    async def ed_health(probe: bool = False) -> dict[str, Any]:
        session = get_session()
        result = session.status()
        if probe and session.authenticated:
            started = time.perf_counter()
            try:
                await session.run(ep.get_surveys)
                result["probe"] = "ok"
            except (
                BaseEcoleDirecteException, ClientError, OSError
            ) as exc:  # pragma: no cover - network dependent
                result["probe"] = "error"
                result["probe_error"] = str(exc)
            result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return result
