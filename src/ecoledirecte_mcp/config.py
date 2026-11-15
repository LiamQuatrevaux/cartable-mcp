# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Configuration and credential handling for the Ecole Directe MCP server."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ecoledirecte_api.const import APIURL, APIVERSION


class ConfigError(RuntimeError):
    """Raised when the server is missing required configuration."""


def config_dir() -> Path:
    """Return the per-user configuration directory."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "ecoledirecte-mcp"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "oui"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} doit être un nombre.") from exc


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else None


def assert_private_file(path: Path, label: str) -> None:
    """Refuse a secret file readable by group or others (POSIX only)."""
    if os.name != "posix":
        return
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        return
    if mode & 0o077:
        raise ConfigError(
            f"{label} ({path}) est accessible aux autres utilisateurs "
            f"(mode {oct(mode)}). Corrige avec : chmod 600 {path}"
        )


def _private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:  # pragma: no cover - exotic filesystems
        pass


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings, all overridable through environment variables."""

    username: str | None = None
    password: str | None = None
    credentials_file: Path | None = None
    qcm_file: Path = field(default_factory=lambda: config_dir() / "qcm.json")
    api_url: str = APIURL
    api_version: str = APIVERSION
    read_only: bool = True
    download_dir: Path = field(default_factory=lambda: config_dir() / "downloads")
    cache_ttl: float = 60.0
    max_download_bytes: int = 25 * 1024 * 1024
    timezone: str = "Europe/Paris"
    min_request_interval: float = 0.2
    request_timeout: float = 45.0
    max_requests_per_minute: int = 120

    def __post_init__(self) -> None:
        object.__setattr__(self, "cache_ttl", min(3600.0, max(0.0, self.cache_ttl)))
        object.__setattr__(
            self,
            "max_download_bytes",
            min(100 * 1024 * 1024, max(1024, self.max_download_bytes)),
        )
        object.__setattr__(
            self, "min_request_interval", min(10.0, max(0.0, self.min_request_interval))
        )
        object.__setattr__(
            self, "request_timeout", min(120.0, max(5.0, self.request_timeout))
        )
        object.__setattr__(
            self,
            "max_requests_per_minute",
            min(600, max(10, self.max_requests_per_minute)),
        )

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from the process environment."""
        default_credentials = config_dir() / "credentials.json"
        credentials_file = _env_path("ED_CREDENTIALS_FILE")
        if credentials_file is None and default_credentials.exists():
            credentials_file = default_credentials

        qcm_file = _env_path("ED_QCM_FILE") or (config_dir() / "qcm.json")
        download_dir = _env_path("ED_DOWNLOAD_DIR") or (config_dir() / "downloads")

        return cls(
            username=os.environ.get("ED_USERNAME"),
            password=os.environ.get("ED_PASSWORD"),
            credentials_file=credentials_file,
            qcm_file=qcm_file,
            api_url=os.environ.get("ED_API_URL", APIURL),
            api_version=os.environ.get("ED_API_VERSION", APIVERSION),
            read_only=_env_bool("ED_READ_ONLY", True),
            download_dir=download_dir,
            cache_ttl=_env_float("ED_CACHE_TTL", 60.0),
            max_download_bytes=int(
                _env_float("ED_MAX_DOWNLOAD_MB", 25.0) * 1024 * 1024
            ),
            timezone=os.environ.get("ED_TIMEZONE", "Europe/Paris"),
            min_request_interval=_env_float("ED_MIN_REQUEST_INTERVAL", 0.2),
            request_timeout=_env_float("ED_REQUEST_TIMEOUT", 45.0),
            max_requests_per_minute=int(
                _env_float("ED_MAX_REQUESTS_PER_MINUTE", 120.0)
            ),
        )

    def has_credentials(self) -> bool:
        """Return True when credentials can be resolved without reading them."""
        if self.username and self.password:
            return True
        return self.credentials_file is not None and self.credentials_file.exists()

    def resolve_credentials(self) -> tuple[str, str]:
        """Return ``(username, password)`` from env or the credentials file."""
        if self.username and self.password:
            return self.username, self.password

        if self.credentials_file is None or not self.credentials_file.exists():
            raise ConfigError(
                "Aucun identifiant Ecole Directe. Définis ED_USERNAME et "
                "ED_PASSWORD, ou crée "
                f"{config_dir() / 'credentials.json'} avec "
                '{"username": "...", "password": "..."}.'
            )

        assert_private_file(self.credentials_file, "Fichier d'identifiants")
        try:
            raw = json.loads(self.credentials_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(
                f"Impossible de lire {self.credentials_file}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigError("Le fichier d'identifiants doit contenir un objet JSON.")

        username = raw.get("username") or raw.get("identifiant")
        password = raw.get("password") or raw.get("motdepasse")
        if not isinstance(username, str) or not isinstance(password, str):
            raise ConfigError(
                "Le fichier d'identifiants doit contenir 'username' et 'password'."
            )
        return username, password


def load_qcm(path: Path) -> dict[str, list[str]]:
    """Load saved QCM answers (question -> single expected answer)."""
    if not path.exists():
        return {}
    assert_private_file(path, "Fichier QCM")
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Fichier QCM illisible ({path}): {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Le fichier QCM doit contenir un objet JSON.")

    answers: dict[str, list[str]] = {}
    for question, value in raw.items():
        if isinstance(value, str):
            answers[str(question)] = [value]
        elif isinstance(value, list):
            values = [str(item) for item in value if isinstance(item, str)]
            if values:
                answers[str(question)] = values
    return answers


def save_qcm(path: Path, answers: dict[str, list[str]]) -> None:
    """Persist QCM answers with restrictive permissions."""
    if not answers:
        return
    _private_dir(path.parent)
    payload = {question: values for question, values in answers.items() if values}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - best effort on exotic filesystems
        pass
