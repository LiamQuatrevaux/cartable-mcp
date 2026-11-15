from pathlib import Path
from typing import Any, cast

import pytest

from ecoledirecte_api.client import EDClient
from ecoledirecte_api.exceptions import EcoleDirecteException, QCMChallengeRequired
from ecoledirecte_mcp.config import Settings
from ecoledirecte_mcp.session import AuthRequired, EdSession, SessionLimitError


def make_session(tmp_path: Path) -> EdSession:
    return EdSession(
        Settings(
            username="eleve",
            password="secret",
            qcm_file=tmp_path / "qcm.json",
            download_dir=tmp_path / "dl",
        )
    )


def test_resolve_student_uses_default(tmp_path):
    session = make_session(tmp_path)
    session._students = [{"id": "1234", "nom": "DOE"}]
    session._student_id = "1234"

    assert session.resolve_student(None) == "1234"
    assert session.resolve_student("1234") == "1234"


def test_resolve_student_rejects_unknown_id(tmp_path):
    session = make_session(tmp_path)
    session._students = [{"id": "1234", "nom": "DOE"}]
    session._student_id = "1234"

    with pytest.raises(ValueError, match="Élève inconnu"):
        session.resolve_student("9999")


def test_resolve_student_requires_login_when_empty(tmp_path):
    session = make_session(tmp_path)

    with pytest.raises(AuthRequired):
        session.resolve_student(None)


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
