from mcp_server import mcp

if __name__ == "__main__":
    mcp.settings.host = "127.0.0.1"
    mcp.settings.port = 5680
    mcp.settings.streamable_http_path = "/mcp"

    mcp.run(transport="streamable-http")
