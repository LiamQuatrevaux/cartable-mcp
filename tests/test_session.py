import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

from ecoledirecte_api.client import EDClient
from ecoledirecte_api.exceptions import (
    EcoleDirecteException,
    LoginException,
    QCMChallengeRequired,
)
from ecoledirecte_mcp.config import Settings, hash_username, load_session, save_session
from ecoledirecte_mcp.session import AuthRequired, EdSession, SessionLimitError


def make_session(tmp_path: Path, **overrides: Any) -> EdSession:
    options: dict[str, Any] = {
        "username": "eleve",
        "password": "secret",
        "qcm_file": tmp_path / "qcm.json",
        "download_dir": tmp_path / "dl",
        "session_file": tmp_path / "session.json",
        "min_request_interval": 0.0,
    }
    options.update(overrides)
    return EdSession(Settings(**options))


def test_resolve_student_uses_default(tmp_path):
    session = make_session(tmp_path)
    session._students = [{"id": "1234", "nom": "DOE"}]
    session._student_id = "1234"

    assert asyncio.run(session.resolve_student(None)) == "1234"
    assert asyncio.run(session.resolve_student("1234")) == "1234"


def test_resolve_student_rejects_unknown_id(tmp_path):
    session = make_session(tmp_path)
    session._students = [{"id": "1234", "nom": "DOE"}]
    session._student_id = "1234"

    with pytest.raises(ValueError, match="Élève inconnu"):
        asyncio.run(session.resolve_student("9999"))


def test_resolve_student_requires_login_when_empty(tmp_path, monkeypatch):
    session = make_session(tmp_path)

    async def no_credentials() -> EDClient:
        raise AuthRequired("Aucun élève associé au compte. Appelle ed_login d'abord.")

    monkeypatch.setattr(session, "client", no_credentials)

    with pytest.raises(AuthRequired, match="Aucun élève associé"):
        asyncio.run(session.resolve_student(None))


def test_resolve_student_logs_in_when_students_unknown(tmp_path, monkeypatch):
    session = make_session(tmp_path)
    calls: list[int] = []

    async def lazy_login() -> EDClient:
        calls.append(1)
        session._students = [{"id": "1234", "nom": "DOE"}]
        session._student_id = "1234"
        return cast(EDClient, None)

    monkeypatch.setattr(session, "client", lazy_login)

    assert asyncio.run(session.resolve_student(None)) == "1234"
    assert calls == [1]

    # Un identifiant explicite ne déclenche aucune connexion.
    session._students = []
    assert asyncio.run(session.resolve_student("4321")) == "4321"
    assert calls == [1]


def test_default_year_uses_account_metadata(tmp_path):
    session = make_session(tmp_path)
    session._accounts = [{"anneeScolaireCourante": "2026-2027"}]

    assert session.default_year() == "2026-2027"


def test_default_year_falls_back_when_metadata_is_null(tmp_path):
    session = make_session(tmp_path)
    session._accounts = [{"id": 7529, "anneeScolaireCourante": None}]

    year = session.default_year()
    assert len(year) == 9 and year[4] == "-"
    assert session.status()["accounts"][0]["anneeScolaireCourante"] == year


def test_status_never_exposes_secrets(tmp_path):
    session = make_session(tmp_path)

    status = session.status()

    assert status["configured"] is True
    assert status["authenticated"] is False
    assert status["read_only"] is True
    assert "secret" not in str(status)


@pytest.mark.asyncio
async def test_submit_qcm_without_pending_question_raises(tmp_path):
    session = make_session(tmp_path)

    with pytest.raises(ValueError, match="Aucun QCM"):
        await session.submit_qcm("42")


@pytest.mark.asyncio
async def test_relogin_closes_previous_client(tmp_path, monkeypatch):
    session = make_session(tmp_path)
    closed = []

    class FakeClient:
        token = "token"

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def on_new_question(self, callback):
            pass

        async def login(self):
            return {"data": {"accounts": []}}

        async def close(self):
            closed.append(True)

    monkeypatch.setattr("ecoledirecte_mcp.session.EDClient", FakeClient)

    old = FakeClient()
    session._client = cast(EDClient, old)
    await session.login(force=True)

    assert closed == [True]


@pytest.mark.asyncio
async def test_login_reuses_authenticated_client(tmp_path, monkeypatch):
    session = make_session(tmp_path)

    class FakeClient:
        token = "token"

    session._client = cast(EDClient, FakeClient())

    async def fail_if_called():
        raise AssertionError("a fresh login should not be attempted")

    monkeypatch.setattr(session, "_login_locked", fail_if_called)

    summary = await session.login()

    assert summary["authenticated"] is True
    assert summary["annee_scolaire"] == session.default_year()


@pytest.mark.asyncio
async def test_login_maps_too_many_sessions(tmp_path, monkeypatch):
    session = make_session(tmp_path)

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def on_new_question(self, callback):
            pass

        async def login(self):
            raise EcoleDirecteException(message="Too many open sessions")

        async def close(self):
            pass

    monkeypatch.setattr("ecoledirecte_mcp.session.EDClient", FakeClient)

    with pytest.raises(SessionLimitError, match="trop de sessions"):
        await session.login()


@pytest.mark.asyncio
async def test_submit_qcm_rejects_answer_outside_propositions(tmp_path):
    session = make_session(tmp_path)
    session._pending = {"question": "Q", "propositions": ["A", "B"]}

    with pytest.raises(ValueError, match="Réponse invalide"):
        await session.submit_qcm("C")

    assert "Q" not in session._qcm


@pytest.mark.asyncio
async def test_submit_qcm_keeps_answer_for_following_question(tmp_path, monkeypatch):
    session = make_session(tmp_path)
    session._pending = {"question": "Q1", "propositions": ["A"]}

    async def fake_login():
        session._pending = {"question": "Q2", "propositions": ["B"]}
        raise QCMChallengeRequired("Q2", ["B"])

    monkeypatch.setattr(session, "login", fake_login)

    with pytest.raises(QCMChallengeRequired):
        await session.submit_qcm("A")

    assert session._qcm["Q1"] == ["A"]
    assert session.settings.qcm_file.exists()


@pytest.mark.asyncio
async def test_submit_qcm_drops_answer_when_same_question_returns(tmp_path, monkeypatch):
    session = make_session(tmp_path)
    session._pending = {"question": "Q1", "propositions": ["A"]}

    async def fake_login():
        session._pending = {"question": "Q1", "propositions": ["A"]}
        raise QCMChallengeRequired("Q1", ["A"])

    monkeypatch.setattr(session, "login", fake_login)

    with pytest.raises(QCMChallengeRequired):
        await session.submit_qcm("A")

    assert "Q1" not in session._qcm


def test_resolve_student_rejects_path_like_id(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    with pytest.raises(ValueError, match="identifiant numérique"):
        asyncio.run(session.resolve_student("../../login"))


def _write_session(tmp_path: Path, *, username: str = "eleve") -> Path:
    path = tmp_path / "session.json"
    save_session(
        path,
        {
            "username_hash": hash_username(username),
            "token": "jeton-abc",
            "token_2fa": None,
            "cn": None,
            "cv": None,
            "student_id": "1234",
            "current_id_login": 7,
            "accounts": [{"id": "1234", "idLogin": 7}],
            "students": [{"id": "1234", "nom": "DOE"}],
        },
    )
    return path


def _age_session(path: Path, seconds: float) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["saved_at"] -= seconds
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)


def test_session_token_is_persisted_with_private_mode(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session._client = EDClient("eleve", "secret", {}, read_only=True)
    session._client.token = "jeton-abc"
    session._accounts = [{"id": "1234", "idLogin": 7}]
    session._students = [{"id": "1234", "nom": "DOE"}]
    session._student_id = "1234"

    session._persist_session()

    path = tmp_path / "session.json"
    assert path.stat().st_mode & 0o777 == 0o600
    stored = load_session(path)
    assert stored is not None
    assert stored["token"] == "jeton-abc"
    assert stored["student_id"] == "1234"
    assert stored["username_hash"] == hash_username("eleve")


def test_restart_reuses_persisted_session_without_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_session(tmp_path)
    session = make_session(tmp_path)

    async def no_login() -> dict[str, Any]:
        raise AssertionError("aucun login ne doit être tenté")

    monkeypatch.setattr(session, "_login_locked", no_login)

    async def scenario() -> tuple[str, str | None]:
        student = await session.resolve_student(None)
        token = session._client.token if session._client is not None else None
        await session.logout()
        return student, token

    assert asyncio.run(scenario()) == ("1234", "jeton-abc")


def test_expired_session_is_discarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_session(tmp_path)
    _age_session(path, 13 * 3600)
    session = make_session(tmp_path)

    async def fallback_login() -> dict[str, Any]:
        raise AuthRequired("identifiants absents")

    monkeypatch.setattr(session, "_login_locked", fallback_login)

    with pytest.raises(AuthRequired):
        asyncio.run(session.client())
    assert not path.exists()


def test_session_from_another_account_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_session(tmp_path, username="autre")
    session = make_session(tmp_path)

    async def fallback_login() -> dict[str, Any]:
        raise AuthRequired("identifiants absents")

    monkeypatch.setattr(session, "_login_locked", fallback_login)

    with pytest.raises(AuthRequired):
        asyncio.run(session.client())
    assert not path.exists()


def test_resolve_student_explains_account_without_student(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    client = EDClient("eleve", "secret", {}, read_only=True)
    client.token = "jeton-abc"
    session._client = client

    with pytest.raises(AuthRequired, match="aucun élève n'est rattaché"):
        asyncio.run(session.resolve_student(None))


def test_login_summary_warns_when_no_student(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    client = EDClient("eleve", "secret", {}, read_only=True)
    client.token = "jeton-abc"
    session._client = client

    assert "avertissement" in session._login_summary()


def test_run_refreshes_rejected_token_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = make_session(tmp_path)
    stale = EDClient("eleve", "secret", {}, read_only=True)
    stale.token = "jeton-perime"
    fresh = EDClient("eleve", "secret", {}, read_only=True)
    fresh.token = "jeton-neuf"
    session._client = stale
    session._students = [{"id": "1234"}]
    session._student_id = "1234"

    logins: list[int] = []

    async def relogin() -> dict[str, Any]:
        logins.append(1)
        session._client = fresh
        return session._login_summary()

    monkeypatch.setattr(session, "_login_locked", relogin)

    seen: list[str | None] = []

    async def call(client: EDClient) -> str:
        seen.append(client.token)
        if client.token == "jeton-perime":
            raise LoginException(message="Le token est invalide")
        return "ok"

    assert asyncio.run(session.run(call)) == "ok"
    assert logins == [1]
    assert seen == ["jeton-perime", "jeton-neuf"]


def test_run_does_not_retry_other_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = make_session(tmp_path)
    client = EDClient("eleve", "secret", {}, read_only=True)
    client.token = "jeton"
    session._client = client

    async def no_login() -> dict[str, Any]:
        raise AssertionError("aucune reconnexion attendue")

    monkeypatch.setattr(session, "_login_locked", no_login)

    async def call(_client: EDClient) -> str:
        raise LoginException(message="Le compte est bloqué")

    with pytest.raises(LoginException, match="bloqué"):
        asyncio.run(session.run(call))


def test_select_account_keeps_session_when_api_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = make_session(tmp_path)
    client = EDClient("eleve", "secret", {}, read_only=True)
    client.token = "jeton-valide"
    session._client = client
    session._accounts = [{"idLogin": 1}, {"idLogin": 2}]

    async def refuse(_id_login: int) -> dict[str, Any]:
        raise EcoleDirecteException(
            path="/renewtoken.awp", message="Changement de compte refusé."
        )

    monkeypatch.setattr(client, "switch_account", refuse)

    with pytest.raises(EcoleDirecteException, match="refusé"):
        asyncio.run(session.select_account(2))

    assert client.token == "jeton-valide"
    assert session.authenticated
