from __future__ import annotations

from .base import BaseLocalConnector


class WxworkLocalConnector(BaseLocalConnector):
    expected_tool_names = (
        "wxwork_get_recent_sessions",
        "wxwork_get_chat_history",
        "wxwork_search_messages",
        "wxwork_get_contacts",
        "wxwork_get_new_messages",
    )
    server_script = "mcp_wxwork_http_server.py"
    cli_connector_name = "wxwork"
    port = 5681
