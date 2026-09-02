from backend_memory_pipeline.mcp.server import get_mcp_server
def main()->None:
    server=get_mcp_server()
    server.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8001,
        streamable_http_path="/mcp",
    )
if __name__=="__main__":
    main()