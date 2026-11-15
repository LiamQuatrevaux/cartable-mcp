# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Helpers shared by all tool modules."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from ecoledirecte_api.client import DownloadedFile
from ecoledirecte_api.exceptions import QCMChallengeRequired

from ..downloads import save_download
from ..runtime import get_session
from ..session import EdSession
from ..validation import require_year

T = TypeVar("T")

NOTES_TTL = 120.0
TIMETABLE_TTL = 120.0
MESSAGES_TTL = 45.0
DOCUMENTS_TTL = 300.0
PROFILE_TTL = 600.0
LIFE_TTL = 120.0
WORKSPACE_TTL = 180.0


def session() -> EdSession:
    return get_session()


def resolve_student(value: str | None) -> str:
    return session().resolve_student(value)


def school_year(value: str | None) -> str:
    validated = require_year(value)
    return validated or session().default_year()


async def cached(
    key: str,
    ttl: float,
    func: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    return await session().fetch(key, ttl, func, *args, **kwargs)


def challenge_response(exc: QCMChallengeRequired) -> dict[str, Any]:
    """Shape a QCM challenge so the agent can ask its user."""
    return {
        "status": "qcm_required",
        "question": exc.question,
        "propositions": exc.propositions,
        "next": "Demande la réponse à l'utilisateur puis appelle "
        "ed_submit_qcm avec la réponse exacte.",
    }


def class_id_for(sid: str) -> str:
    """Return the class id attached to the student's account."""
    for account in session().accounts:
        candidates: list[dict[str, Any]] = [account]
        children = account.get("eleves")
        if isinstance(children, list):
            candidates.extend(child for child in children if isinstance(child, dict))
        for candidate in candidates:
            if str(candidate.get("id")) != sid:
                continue
            profile = candidate.get("profile")
            if isinstance(profile, dict) and isinstance(profile.get("classe"), dict):
                value = profile["classe"].get("id")
                if value is not None:
                    return str(value)
    raise ValueError(
        "Classe inconnue pour cet élève : passe classe_id explicitement."
    )


def store(file: DownloadedFile, fallback: str) -> dict[str, Any]:
    """Persist a downloaded file inside the configured directory."""
    settings = session().settings
    return save_download(
        settings.download_dir,
        file.content,
        filename=file.filename,
        content_type=file.content_type,
        fallback=fallback,
    )


def basename_of(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "fichier"


def download_dir() -> Path:
    return session().settings.download_dir
