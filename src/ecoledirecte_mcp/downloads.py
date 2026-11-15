# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Save downloaded attachments inside a controlled directory."""

from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path
from typing import Any

_UNSAFE = re.compile(r"[^A-Za-z0-9._ ()\-]+")
_SUFFIXES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "text/plain": ".txt",
    "text/html": ".html",
    "application/zip": ".zip",
}


def _safe_name(filename: str, content_type: str | None, fallback: str) -> str:
    name = Path(filename).name.strip() or fallback
    name = _UNSAFE.sub("_", name).strip(" .") or fallback
    name = name[:120]
    if "." not in name:
        suffix = _SUFFIXES.get((content_type or "").split(";")[0].strip())
        if suffix is None:
            suffix = mimetypes.guess_extension(
                (content_type or "").split(";")[0].strip() or ""
            )
        name += suffix or ""
    # Un nom ne doit jamais pouvoir sortir du dossier de téléchargement.
    if name in {".", ".."} or "/" in name or "\\" in name:
        name = fallback
    return name


def save_download(
    directory: Path,
    content: bytes,
    *,
    filename: str | None,
    content_type: str | None = None,
    fallback: str = "fichier",
) -> dict[str, Any]:
    """Write ``content`` and return a path/size descriptor."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:  # pragma: no cover - exotic filesystems
        pass

    root = directory.resolve()
    name = _safe_name(filename or "", content_type, fallback)
    path = (root / name).resolve()
    if path.parent != root:
        raise ValueError("Nom de fichier refusé : sortie du dossier autorisé.")

    # O_EXCL + O_NOFOLLOW : ni écrasement, ni suivi de lien symbolique.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    counter = 1
    while True:
        try:
            descriptor = os.open(path, flags, 0o600)
            break
        except FileExistsError:
            path = (root / f"{Path(name).stem}-{counter}{Path(name).suffix}").resolve()
            counter += 1
            if path.parent != root:
                raise ValueError("Nom de fichier refusé : sortie du dossier autorisé.")
        except OSError as exc:
            raise ValueError(f"Écriture refusée dans {root} : {exc}") from exc

    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)

    return {
        "path": str(path),
        "filename": path.name,
        "size": len(content),
        "content_type": content_type,
    }
