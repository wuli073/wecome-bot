from __future__ import annotations

from .base import BaseLocalConnector


class WechatLocalConnector(BaseLocalConnector):
    expected_tool_names = (
        "get_recent_sessions",
        "get_chat_history",
        "search_messages",
        "get_contacts",
        "get_contact_tags",
        "get_tag_members",
        "get_new_messages",
        "decode_image",
        "decode_file_message",
        "decode_record_item",
        "decode_transfer",
        "decode_refer",
        "decode_location",
        "get_chat_images",
        "get_voice_messages",
        "decode_voice",
        "transcribe_voice",
    )
    server_script = "mcp_http_server.py"
    cli_connector_name = "wechat"
    port = 5680
