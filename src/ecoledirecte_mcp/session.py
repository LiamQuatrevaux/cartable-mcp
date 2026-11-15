# SPDX-FileCopyrightText: 2026 LiamQuatrevaux
# SPDX-License-Identifier: LGPL-3.0-or-later
#

"""Session lifecycle for the Ecole Directe MCP server."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from typing import Any, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ecoledirecte_api.client import EDClient
from ecoledirecte_api.exceptions import LoginException, QCMChallengeRequired

from .cache import TTLCache
from .config import (
    ConfigError,
    Settings,
    clear_session,
    hash_username,
    load_qcm,
    load_session,
    save_qcm,
    save_session,
)
from .validation import require_numeric_id

T = TypeVar("T")

LOGGER = logging.getLogger(__name__)


class AuthRequired(RuntimeError):
    """Raised when the API cannot be used without a successful login."""


class SessionLimitError(RuntimeError):
    """Raised when Ecole Directe refuses to open another session."""


class EdSession:
    """Owns the single authenticated client and serializes API calls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_version = settings.api_version
        self._client: EDClient | None = None
        self._accounts: list[dict[str, Any]] = []
        self._students: list[dict[str, Any]] = []
        self._student_id: str | None = None
        self._current_id_login: int | None = None
        self._pending: dict[str, Any] | None = None
        self._login_lock = asyncio.Lock()
        self._api_lock = asyncio.Lock()
        self._cache = TTLCache()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._last_request = 0.0
        self._request_times: deque[float] = deque()
        self._request_count = 0
        self._last_latency_ms: float | None = None
        self._saved_token: str | None = None
        self._qcm = load_qcm(settings.qcm_file)

    # -- state ------------------------------------------------------------

    @property
    def accounts(self) -> list[dict[str, Any]]:
        return self._accounts

    @property
    def students(self) -> list[dict[str, Any]]:
        return self._students

    @property
    def student_id(self) -> str | None:
        return self._student_id

    @property
    def pending_challenge(self) -> dict[str, Any] | None:
        return self._pending

    @property
    def authenticated(self) -> bool:
        return self._client is not None and bool(self._client.token)

    def status(self) -> dict[str, Any]:
        """Return a secret-free snapshot of the session."""
        return {
            "configured": self.settings.has_credentials(),
            "authenticated": self.authenticated,
            "read_only": True,
            "api_version": self.api_version,
            "api_url": self.settings.api_url,
            "student_id": self._student_id,
            "students": self._students,
            "accounts": [
                {
                    "id": account.get("id"),
                    "idLogin": account.get("idLogin"),
                    "nom": account.get("nom"),
                    "prenom": account.get("prenom"),
                    "typeCompte": account.get("typeCompte"),
                    "anneeScolaireCourante": self._account_year(account),
                }
                for account in self._accounts
            ],
            "pending_qcm": self._pending is not None,
            "cache": self._cache.stats(),
            "metrics": {
                "requests": self._request_count,
                "last_latency_ms": self._last_latency_ms,
                "max_requests_per_minute": self.settings.max_requests_per_minute,
                "request_timeout_s": self.settings.request_timeout,
            },
            "download_dir": str(self.settings.download_dir),
        }

    # -- authentication ---------------------------------------------------

    async def client(self) -> EDClient:
        """Return a logged-in client, reusing the persisted session if any."""
        if self.authenticated and self._client is not None:
            return self._client
        async with self._login_lock:
            missing = self._client is None or not self._client.token
            if missing and not await self._restore_locked():
                await self._login_locked()
        assert self._client is not None
        return self._client

    def _build_client(self, username: str, password: str) -> EDClient:
        """Create an unauthenticated client wired to the challenge callback."""
        client = EDClient(
            username,
            password,
            self._qcm,
            server_endpoint=self.settings.api_url,
            api_version=self.settings.api_version,
            read_only=True,
            timeout=self.settings.request_timeout,
        )
        client.on_new_question(self._store_challenge)
        return client

    async def _restore_locked(self) -> bool:
        """Reattach the session written by the previous process, if still valid.

        Reusing the token avoids opening a new Ecole Directe session on every
        restart, which is what drives the ``Too many open sessions`` answer.
        """
        path = self.settings.session_file
        if path is None:
            return False
        stored = load_session(path)
        if stored is None:
            return False
        if time.time() - stored["saved_at"] > self.settings.session_ttl:
            clear_session(path)
            return False
        try:
            username, password = self.settings.resolve_credentials()
        except ConfigError:
            return False
        if stored["username_hash"] != hash_username(username):
            clear_session(path)
            return False

        client = self._build_client(username, password)
        client.restore_session(
            stored["token"],
            token_2fa=stored["token_2fa"],
            cn=stored["cn"],
            cv=stored["cv"],
        )
        self._client = client
        self._accounts = stored["accounts"]
        self._students = stored["students"]
        self._student_id = stored["student_id"]
        self._current_id_login = stored["current_id_login"]
        self._saved_token = stored["token"]
        LOGGER.info("Session réutilisée depuis %s (sans nouvel identifiant).", path)
        return True

    def _persist_session(self) -> None:
        """Write the current token to disk so a restart reuses it."""
        path = self.settings.session_file
        client = self._client
        if path is None or client is None or not client.token:
            return
        if client.token == self._saved_token:
            return
        try:
            username, _ = self.settings.resolve_credentials()
        except ConfigError:
            return
        try:
            save_session(
                path,
                {
                    "username_hash": hash_username(username),
                    "token": client.token,
                    "token_2fa": getattr(client, "token_2fa", None),
                    "cn": getattr(client, "cn", None),
                    "cv": getattr(client, "cv", None),
                    "student_id": self._student_id,
                    "current_id_login": self._current_id_login,
                    "accounts": self._accounts,
                    "students": self._students,
                },
            )
        except OSError as exc:  # pragma: no cover - disque plein, droits, etc.
            LOGGER.warning("Session non enregistrée (%s): %s", path, exc)
            return
        self._saved_token = client.token

    async def login(self, *, force: bool = False) -> dict[str, Any]:
        """Open a session, reusing an already authenticated client.

        ``ed_login`` is often called at the start of a conversation.  Creating
        a new Ecole Directe token each time leaks server-side sessions (the
        API eventually answers ``Too many open sessions``), so only force a
        fresh login when explicitly requested or when a QCM is pending.
        """
        async with self._login_lock:
            if (
                not force
                and self._pending is None
                and self.authenticated
                and self._client is not None
            ):
                return self._login_summary()
            return await self._login_locked()

    async def _login_locked(self) -> dict[str, Any]:
        try:
            username, password = self.settings.resolve_credentials()
        except ConfigError as exc:
            raise AuthRequired(str(exc)) from exc

        client = self._build_client(username, password)

        try:
            payload = await client.login()
        except QCMChallengeRequired:
            await client.close()
            raise
        except Exception as exc:
            await client.close()
            message = str(exc).lower()
            if "too many open sessions" in message or "trop de sessions" in message:
                raise SessionLimitError(
                    "Ecole Directe refuse une nouvelle session : trop de sessions "
                    "sont encore ouvertes. Réutilise la session existante ou "
                    "attends quelques minutes avant de rappeler ed_login."
                ) from exc
            raise

        if not isinstance(payload, dict):
            await client.close()
            raise LoginException(message="Réponse de connexion inattendue.")

        data = payload.get("data")
        accounts = []
        if isinstance(data, dict) and isinstance(data.get("accounts"), list):
            accounts = [a for a in data["accounts"] if isinstance(a, dict)]

        previous = self._client
        self._client = client
        if previous is not None and previous is not client:
            with suppress(Exception):
                await previous.close()
        self._accounts = accounts
        self._students = _collect_students(accounts)
        if self._student_id is None or self._student_id not in {
            student["id"] for student in self._students
        }:
            self._student_id = self._students[0]["id"] if self._students else None
        if self._current_id_login is None and accounts:
            id_login = accounts[0].get("idLogin")
            self._current_id_login = (
                int(id_login) if isinstance(id_login, int | str) else None
            )

        save_qcm(self.settings.qcm_file, self._qcm)
        self._pending = None
        self._persist_session()
        return self._login_summary()

    async def _store_challenge(self, qcm: dict[str, list[str]]) -> None:
        """Callback invoked by the client when a new QCM question appears."""
        if not qcm:
            raise QCMChallengeRequired("", [])
        question = next(reversed(qcm))
        propositions = [str(item) for item in qcm[question]]
        self._pending = {"question": question, "propositions": propositions}
        raise QCMChallengeRequired(question, propositions)

    async def submit_qcm(self, answer: str) -> dict[str, Any]:
        """Store the answer to the pending question and retry the login."""
        pending = self._pending
        if pending is None:
            raise ValueError(
                "Aucun QCM en attente : appelle ed_login pour en obtenir un."
            )
        question = str(pending["question"])
        propositions = [str(item) for item in pending.get("propositions") or []]
        cleaned = answer.strip()
        if propositions and cleaned not in propositions:
            raise ValueError(
                f"Réponse invalide pour « {question} ». Propositions : "
                + " | ".join(propositions)
            )

        self._qcm[question] = [cleaned]
        self._pending = None
        try:
            return await self.login()
        except QCMChallengeRequired:
            next_pending = self.pending_challenge
            if next_pending is None:
                raise
            if next_pending.get("question") == question:
                # La même question revient : la réponse a été refusée.
                self._qcm.pop(question, None)
            # Question suivante : la réponse précédente est acceptée, on la
            # persiste pour survivre à un redémarrage du serveur.
            save_qcm(self.settings.qcm_file, self._qcm)
            raise
        except Exception:
            self._qcm.pop(question, None)
            raise

    async def logout(self) -> None:
        """Close the HTTP session and forget in-memory authentication."""
        async with self._login_lock:
            client = self._client
            self._client = None
            if client is not None:
                await client.close()
        self._accounts = []
        self._students = []
        self._student_id = None
        self._current_id_login = None
        self._pending = None
        self._cache.clear()
        self._key_locks.clear()
        self._saved_token = None
        if self.settings.session_file is not None:
            clear_session(self.settings.session_file)

    async def select_account(self, id_login: int) -> dict[str, Any]:
        """Switch the API token to another account of the same login."""
        account = next(
            (a for a in self._accounts if a.get("idLogin") == id_login), None
        )
        if account is None:
            raise ValueError(f"Compte inconnu : {id_login}.")
        client = await self.client()
        async with self._api_lock:
            await client.switch_account(id_login)
        self._current_id_login = id_login
        students = _collect_students([account])
        if students:
            self._student_id = students[0]["id"]
        self._cache.clear()
        self._persist_session()
        return self._login_summary()

    def _login_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "authenticated": self.authenticated,
            "student_id": self._student_id,
            "students": self._students,
            "accounts": self.status()["accounts"],
            "annee_scolaire": self.default_year(),
            "api_version": self.api_version,
        }
        if self.authenticated and not self._students:
            summary["avertissement"] = (
                "Connexion réussie, mais aucun élève n'est rattaché à ce compte : "
                "les outils qui exigent un élève resteront indisponibles."
            )
        return summary

    # -- calls ------------------------------------------------------------

    async def resolve_student(self, student_id: str | None = None) -> str:
        """Validate and return the student id used by every data endpoint.

        The id is checked against the strict numeric validator before it can
        reach a URL path, and against the accounts of the current login when
        they are already known. Without an explicit id the session logs in on
        first use, so the student list is known again after a restart.
        """
        if student_id is None and not self._students:
            await self.client()
        known = {student["id"]: student for student in self._students}
        if student_id is not None:
            candidate = require_numeric_id(str(student_id), "student_id")
            if known and candidate not in known:
                raise ValueError(
                    "Élève inconnu pour ce compte. Identifiants disponibles : "
                    + ", ".join(sorted(known))
                )
            return candidate
        if self._student_id is None:
            if self.authenticated:
                raise AuthRequired(
                    "Connexion Ecole Directe réussie, mais aucun élève n'est "
                    "rattaché à ce compte : il n'y a donc aucun identifiant "
                    "d'élève à utiliser. Le compte est probablement personnel "
                    "(professeur, vie scolaire) ou parental sans enfant actif."
                )
            raise AuthRequired(
                "Aucun élève associé au compte. Appelle ed_login d'abord."
            )
        return self._student_id

    def _account_year(self, account: dict[str, Any]) -> str:
        """Return a usable school year for one account."""
        year = account.get("anneeScolaireCourante")
        if isinstance(year, str) and year.strip():
            return year.strip()
        return self.default_year()

    def _fallback_year(self) -> str:
        """Compute the school year in the configured timezone."""
        try:
            tz = ZoneInfo(self.settings.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            tz = None
        now = datetime.now(tz)
        start = now.year if now.month >= 8 else now.year - 1
        return f"{start}-{start + 1}"

    def default_year(self) -> str:
        """Current school year from account metadata, else computed."""
        for account in self._accounts:
            year = account.get("anneeScolaireCourante")
            if isinstance(year, str) and year.strip():
                return year.strip()
        return self._fallback_year()

    async def _throttle(self) -> None:
        """Apply the per-minute budget, then the minimum gap between calls."""
        limit = self.settings.max_requests_per_minute
        while True:
            now = time.monotonic()
            while self._request_times and now - self._request_times[0] >= 60.0:
                self._request_times.popleft()
            if len(self._request_times) < limit:
                break
            await asyncio.sleep(max(0.05, 60.0 - (now - self._request_times[0])))
        delay = self.settings.min_request_interval - (
            time.monotonic() - self._last_request
        )
        if delay > 0:
            await asyncio.sleep(delay)

    async def run(
        self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
    ) -> T:
        """Run one API call, serialized, rate-limited and measured.

        A token Ecole Directe rejects (code 520, typically a persisted token
        that expired while the service was idle) is replaced by a fresh login
        and the call is retried once, so a stale token never surfaces as an
        error to the user.
        """
        client = await self.client()
        async with self._api_lock:
            try:
                return await self._invoke(client, func, args, kwargs)
            except LoginException as exc:
                if not _is_invalid_token(exc):
                    raise
                LOGGER.info("Token refusé par l'API, reconnexion transparente.")
                client = await self._reconnect_locked()
                return await self._invoke(client, func, args, kwargs)

    async def _invoke(
        self,
        client: EDClient,
        func: Callable[..., Awaitable[T]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> T:
        """Run one call against ``client`` and keep the metrics up to date."""
        await self._throttle()
        started = time.perf_counter()
        try:
            return await func(client, *args, **kwargs)
        finally:
            self._last_request = time.monotonic()
            self._request_times.append(self._last_request)
            self._request_count += 1
            self._last_latency_ms = round((time.perf_counter() - started) * 1000, 1)
            # Un renouvellement de token doit survivre au redémarrage.
            if self._client is not None and self._client.token != self._saved_token:
                self._persist_session()

    async def _reconnect_locked(self) -> EDClient:
        """Open a fresh session after the current token was rejected."""
        async with self._login_lock:
            await self._login_locked()
        assert self._client is not None
        return self._client

    async def fetch(
        self,
        key: str,
        ttl: float,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Return a cached value, deduplicating concurrent misses."""
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        lock = self._key_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._key_locks[key] = lock
        try:
            async with lock:
                cached = self._cache.get(key)
                if cached is not None:
                    return cached
                value = await self.run(func, *args, **kwargs)
                self._cache.set(key, value, ttl)
                return value
        finally:
            if not lock.locked() and self._key_locks.get(key) is lock:
                self._key_locks.pop(key, None)

    def cache_stats(self) -> dict[str, int]:
        return self._cache.stats()


_INVALID_TOKEN_HINTS = (
    "token est invalide",
    "token is invalid",
    "no active api session",
)


def _is_invalid_token(exc: BaseException) -> bool:
    """Return True when the API rejected the token rather than the request."""
    message = str(exc).lower()
    return any(hint in message for hint in _INVALID_TOKEN_HINTS)


def _collect_students(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    students: list[dict[str, Any]] = []
    seen: set[str] = set()
    for account in accounts:
        candidates: list[dict[str, Any]] = []
        if str(account.get("typeCompte")) == "E":
            candidates.append(account)
        children = account.get("eleves")
        if isinstance(children, list):
            candidates.extend(child for child in children if isinstance(child, dict))
        for candidate in candidates:
            student_id = candidate.get("id")
            if student_id is None:
                continue
            key = str(student_id)
            if key in seen:
                continue
            seen.add(key)
            profile = candidate.get("profile")
            classe = None
            if isinstance(profile, dict) and isinstance(profile.get("classe"), dict):
                classe = profile["classe"].get("id")
            students.append(
                {
                    "id": key,
                    "nom": candidate.get("nom"),
                    "prenom": candidate.get("prenom"),
                    "classe_id": str(classe) if classe is not None else None,
                    "idLogin": account.get("idLogin"),
                    "etablissement": candidate.get("nomEtablissement"),
                }
            )
    return students
