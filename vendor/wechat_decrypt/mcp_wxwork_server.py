from mcp.server.fastmcp import FastMCP

import wxwork_query


mcp = FastMCP(
    "wxwork-readonly",
    instructions=(
        "Read-only MCP server for querying WeCom (WXWork) sessions, contacts, "
        "and chat history from wxwork_decrypted."
    ),
)


@mcp.tool()
def wxwork_get_recent_sessions(limit: int = 20):
    """Return recent WeCom sessions ordered by the last message time descending."""
    return wxwork_query.get_recent_sessions(limit=limit)


@mcp.tool()
def wxwork_get_chat_history(
    chat_name: str,
    limit: int = 20,
    offset: int = 0,
    start_time: str = "",
    end_time: str = "",
):
    """Return paged WeCom chat history by display name or conversation_id."""
    return wxwork_query.get_chat_history(
        chat_name=chat_name,
        limit=limit,
        offset=offset,
        start_time=start_time,
        end_time=end_time,
    )


@mcp.tool()
def wxwork_search_messages(
    keyword: str,
    chat_name: str = "",
    limit: int = 20,
    offset: int = 0,
    start_time: str = "",
    end_time: str = "",
):
    """Search WeCom messages globally or within a single session."""
    return wxwork_query.search_messages(
        keyword=keyword,
        chat_name=chat_name,
        limit=limit,
        offset=offset,
        start_time=start_time,
        end_time=end_time,
    )


@mcp.tool()
def wxwork_get_contacts(query: str = "", limit: int = 50):
    """Return WeCom contacts from user.db."""
    return wxwork_query.get_contacts(query=query, limit=limit)


@mcp.tool()
def wxwork_get_new_messages(limit: int = 20):
    """Query the latest messages currently stored in the WeCom database."""
    return wxwork_query.get_new_messages(limit=limit)
