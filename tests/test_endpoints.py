import json
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from ecoledirecte_api import endpoints as ep
from ecoledirecte_api.exceptions import EcoleDirecteException


def make_client() -> Mock:
    client = Mock()
    client.api_version = "4.104.3"
    client.request = AsyncMock(return_value={"code": 200, "data": []})
    return client


def body_of(call: Any) -> dict[str, Any]:
    payload: str = call.kwargs["payload"]
    assert payload.startswith("data=")
    body: dict[str, Any] = json.loads(payload.removeprefix("data="))
    return body


@pytest.mark.asyncio
async def test_get_student_uses_details_route():
    client = make_client()

    await ep.get_student(client, "1234")

    call = client.request.await_args
    assert call.args == ("POST", "/eleves/1234/details.awp")
    assert body_of(call) == {}


@pytest.mark.asyncio
async def test_get_messages_uses_student_mailbox_params():
    client = make_client()

    await ep.get_messages(
        client,
        "1234",
        folder="received",
        annee="2025-2026",
        query="sortie",
        unread_only=True,
        page=2,
        per_page=10,
    )

    call = client.request.await_args
    assert call.args == ("POST", "/eleves/1234/messages.awp")
    params = call.kwargs["params"]
    assert params["verbe"] == "get"
    assert params["v"] == "4.104.3"
    assert params["typeRecuperation"] == "received"
    assert params["onlyRead"] == "true"
    assert params["page"] == "2"
    assert params["itemsPerPage"] == "10"
    assert body_of(call) == {"anneeMessages": "2025-2026"}


@pytest.mark.asyncio
async def test_get_timetable_sends_valid_json():
    client = make_client()

    await ep.get_timetable(client, "1234", "2026-09-01", "2026-09-07")

    call = client.request.await_args
    assert call.args == ("POST", "/E/1234/emploidutemps.awp")
    assert body_of(call) == {
        "dateDebut": "2026-09-01",
        "dateFin": "2026-09-07",
        "avecTrous": False,
    }


@pytest.mark.asyncio
async def test_notes_body_uses_valid_json():
    client = make_client()

    await ep.get_notes(client, "1234", "2024-2025")

    assert body_of(client.request.await_args) == {"anneeScolaire": "2024-2025"}


@pytest.mark.asyncio
async def test_documents_uses_current_year_archive():
    client = make_client()

    await ep.get_documents(client, "")

    params = client.request.await_args.kwargs["params"]
    assert params["archive"] == ""
    assert params["verbe"] == "get"


@pytest.mark.asyncio
async def test_forms_send_student_entity():
    client = make_client()

    await ep.get_forms(client, "1234", "2025-2026")

    call = client.request.await_args
    assert call.args == ("POST", "/edforms.awp")
    assert body_of(call) == {
        "anneeForms": "2025-2026",
        "typeEntity": "E",
        "idEntity": 1234,
    }


@pytest.mark.asyncio
async def test_canteen_slot_compacts_date():
    client = make_client()

    await ep.check_canteen_slot(client, "1234", "7", "2026-09-05")

    assert (
        client.request.await_args.args[1]
        == "/E/1234/commandesPassage/pointsDePassage/7/20260905.awp"
    )


@pytest.mark.asyncio
async def test_cloud_uses_folder_param():
    client = make_client()

    await ep.get_cloud(client, "1234", folder="\\\\RNE\\E\\1234\\Cours")

    call = client.request.await_args
    assert call.args == ("POST", "/cloud/E/1234.awp")
    assert call.kwargs["params"]["idfolder"] == "\\\\RNE\\E\\1234\\Cours"


@pytest.mark.asyncio
async def test_class_life_keeps_partial_results():
    client = make_client()
    client.request = AsyncMock(
        side_effect=[
            {"data": {"ok": 1}},
            EcoleDirecteException(message="route désactivée"),
        ]
    )

    result = await ep.get_class_life(client, "44")

    assert result["classes"] == {"data": {"ok": 1}}
    assert "error" in result["r"]
