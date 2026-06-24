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
    monitor_script = "wxwork_message_monitor.py"
    cli_connector_name = "wxwork"
    port = 5681

    def build_start_command(self, role: str = "mcp", runtime_dir: str | None = None) -> list[str]:
        command = super().build_start_command(role=role, runtime_dir=runtime_dir)
        if role == "monitor":
            if not runtime_dir:
                raise ValueError("runtime_dir is required for monitor role")
            command.extend(["--runtime-dir", runtime_dir])
        return command
