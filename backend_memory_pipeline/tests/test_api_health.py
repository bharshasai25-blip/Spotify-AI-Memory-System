from fastapi.testclient import TestClient
from backend_memory_pipeline.api.app import app
client=TestClient(app)
def test_health_endpoint_returns_healthy_status():
    response=client.get("/v1/health")
    assert response.status_code==200
    body=response.json()
    assert body["schema_version"]=="1.0"
    assert body["status"]=="healthy"
    assert body["service"]=="spotify-ai-memory-api"
    assert body["version"]=="1.0.0"
    assert body["timestamp"]
    assert body["checks"]["api"]=="healthy"