from qdrant_client import QdrantClient
def test_qdrant_connection():
    client=QdrantClient(url="http://localhost:6333")
    info=client.get_collections()
    assert info is not None