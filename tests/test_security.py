import asyncio
import os
from pathlib import Path

import pytest

from ecoledirecte_api.client import EDClient
from ecoledirecte_api.exceptions import LoginException, ReadOnlyViolation
from ecoledirecte_mcp.config import ConfigError, Settings, save_qcm
from ecoledirecte_mcp.downloads import save_download
from ecoledirecte_mcp.session import EdSession
from ecoledirecte_mcp.validation import (
    clamp,
    require_date,
    require_numeric_id,
    require_range,
    require_token_id,
    require_year,
)


def test_exception_redacts_password():
    exception = LoginException(
        path="/login.awp",
        payload='data={"identifiant":"eleve","motdepasse":"s3cret!"}',
    )

    assert "s3cret!" not in str(exception)
    assert "***" in str(exception)


def test_exception_redacts_token_in_dict_message():
    exception = LoginException(
        path="/eleves/1/details.awp",
        message={"code": 403, "token": "secret-token", "host": "HTTP1"},
    )

    assert "secret-token" not in str(exception)
    assert "'token': '***'" in str(exception)


def test_read_only_client_refuses_write_verbs():
    client = EDClient("u", "p", {}, read_only=True)

    with pytest.raises(ReadOnlyViolation):
        asyncio.run(
            client.request(
                "POST", "/Eleves/123/cahierdetexte.awp", params={"verbe": "put"}
            )
        )


def test_read_only_client_accepts_get_verbs():
    client = EDClient("u", "p", {}, read_only=True)

    client._enforce_read_only({"verbe": "get"}, "/eleves/1/notes.awp")


def test_read_only_client_accepts_list_verb():
    client = EDClient("u", "p", {}, read_only=True)

    client._enforce_read_only({"verbe": "list"}, "/edforms.awp")


def test_credentials_file_must_be_private(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions only")

    credentials = tmp_path / "credentials.json"
    credentials.write_text('{"username": "u", "password": "p"}', encoding="utf-8")
    credentials.chmod(0o644)

    settings = Settings(credentials_file=credentials, qcm_file=tmp_path / "qcm.json")
    with pytest.raises(ConfigError, match="chmod 600"):
        settings.resolve_credentials()

    credentials.chmod(0o600)
    assert settings.resolve_credentials() == ("u", "p")


def test_download_cannot_escape_directory(tmp_path: Path) -> None:
    result = save_download(
        tmp_path / "downloads", b"payload", filename="../../evil.txt"
    )

    path = Path(result["path"])
    assert path.parent == (tmp_path / "downloads").resolve()
    assert path.name == "evil.txt"
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_dates_are_strict():
    assert require_date("2026-09-01") == "2026-09-01"
    with pytest.raises(ValueError):
        require_date("2026-09-01/../../login")
    with pytest.raises(ValueError):
        require_date("2026-13-01")
    assert require_range("2026-09-01", "2026-09-07") == ("2026-09-01", "2026-09-07")
    with pytest.raises(ValueError):
        require_range("2026-09-07", "2026-09-01")


def test_ids_years_and_limits_are_strict():
    assert require_numeric_id("1234") == "1234"
    with pytest.raises(ValueError):
        require_numeric_id("../1234")
    assert require_token_id("msg-1_A") == "msg-1_A"
    with pytest.raises(ValueError):
        require_token_id("msg/1")
    assert require_year("2025-2026") == "2025-2026"
    with pytest.raises(ValueError):
        require_year("2025-2027")
    assert clamp(9999, 1, 200) == 200


@pytest.mark.asyncio
async def test_concurrent_fetches_share_one_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = EdSession(
        Settings(
            username="u",
            password="p",
            qcm_file=tmp_path / "qcm.json",
            download_dir=tmp_path / "dl",
            min_request_interval=0,
        )
    )
    calls = 0

    async def fake_run(func, *args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.02)
        return {"ok": True}

    monkeypatch.setattr(session, "run", fake_run)

    results = await asyncio.gather(
        session.fetch("key", 60, fake_run),
        session.fetch("key", 60, fake_run),
    )

    assert list(results) == [{"ok": True}, {"ok": True}]
    assert calls == 1


def test_token_rotation_is_captured():
    client = EDClient("u", "p", {})
    client._session = type("Session", (), {"headers": {}})()

    response = type("Response", (), {"headers": {"x-token": "new-token"}})()

    client._capture_tokens(response)

    assert client.token == "new-token"
    assert client._session.headers["x-token"] == "new-token"


def test_raw_query_denylist():
    from ecoledirecte_mcp.tools.meta import is_allowed_path

    assert is_allowed_path("/eleves/123/timeline.awp")
    assert not is_allowed_path("/login.awp")
    assert not is_allowed_path("/connexion/doubleauth.awp")
    assert not is_allowed_path("/telechargement.awp")
    assert not is_allowed_path("/eleves/../../login.awp")
    assert not is_allowed_path("https://evil.example/x.awp")


def test_read_only_client_refuses_write_verbe_in_body() -> None:
    client = EDClient("u", "p", {}, read_only=True)

    with pytest.raises(ReadOnlyViolation):
        client._enforce_read_only(
            {"verbe": "get"}, "/eleves/1/notes.awp", 'data={"verbe": "put"}'
        )

    # Corps illisible mais qui mentionne verbe : refusé par prudence.
    with pytest.raises(ReadOnlyViolation):
        client._enforce_read_only(
            {"verbe": "get"}, "/eleves/1/notes.awp", 'data={"verbe": "put"'
        )

    # Corps légitime : la lecture reste autorisée.
    client._enforce_read_only(
        {"verbe": "get"}, "/eleves/1/notes.awp", 'data={"anneeScolaire": "x"}'
    )


def test_save_qcm_creates_private_file(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permissions only")

    path = tmp_path / "qcm.json"
    save_qcm(path, {"QCM": ["A"]})

    assert path.read_text(encoding="utf-8").lstrip().startswith("{")
    assert path.stat().st_mode & 0o777 == 0o600
