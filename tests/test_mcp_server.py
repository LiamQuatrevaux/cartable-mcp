from pathlib import Path

import pytest
from mcp.server.mcpserver import MCPServer

from ecoledirecte_mcp.config import Settings
from ecoledirecte_mcp.server import TOOL_MODULES, build_server

WRITE_PREFIXES = (
    "ed_send",
    "ed_delete",
    "ed_reply",
    "ed_order",
    "ed_submit_form",
    "ed_mark",
)


@pytest.fixture
def server(tmp_path: Path) -> MCPServer:
    return build_server(
        Settings(
            username="eleve",
            password="secret",
            qcm_file=tmp_path / "qcm.json",
            download_dir=tmp_path / "dl",
        )
    )


@pytest.mark.asyncio
async def test_all_domains_register(server):
    tools = await server.list_tools()
    names = {tool.name for tool in tools}

    assert len(TOOL_MODULES) == 11
    assert len(tools) >= 55
    assert {
        "ed_login",
        "ed_get_context",
        "ed_get_profile",
        "ed_get_period_report",
        "ed_get_homework_day",
        "ed_get_week",
        "ed_get_attendance_summary",
        "ed_get_message",
        "ed_list_documents",
        "ed_list_canteen_orders",
        "ed_list_cloud",
        "ed_get_catalog",
    } <= names


@pytest.mark.asyncio
async def test_tools_are_prefixed_and_documented(server):
    for tool in await server.list_tools():
        assert tool.name.startswith("ed_")
        assert tool.description
        assert len(tool.description) > 20


@pytest.mark.asyncio
async def test_server_is_read_only(server):
    names = {tool.name for tool in await server.list_tools()}

    for name in names:
        assert not name.startswith(WRITE_PREFIXES), name


@pytest.mark.asyncio
async def test_catalog_matches_registered_tools(server):
    from ecoledirecte_mcp.tools.meta import CATALOG

    catalogued = {name for tools in CATALOG.values() for name in tools}
    registered = {tool.name for tool in await server.list_tools()}

    assert catalogued == registered
