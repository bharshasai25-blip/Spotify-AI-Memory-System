from unittest.mock import Mock,patch
from backend_memory_pipeline.mcp.app import main
def test_mcp_app_main_runs_streamable_http():
    mock_server=Mock()
    with patch(
        "backend_memory_pipeline.mcp.app.get_mcp_server",
        return_value=mock_server,
    ):
        main()
    mock_server.run.assert_called_once_with(
        transport="streamable-http",
        host="127.0.0.1",
        port=8001,
        streamable_http_path="/mcp",
    )