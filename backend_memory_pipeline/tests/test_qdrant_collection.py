from qdrant_client import QdrantClient
from backend_memory_pipeline.persistence.qdrant.embedding_store import QdrantEmbeddingStore
def test_qdrant_collection_is_created_with_expected_vector_configuration():
    store=QdrantEmbeddingStore(
        url="http://localhost:6333",
        collection_name="spotify_memory_embeddings_test"
    )
    store.verify_connectivity()
    store.ensure_collection(dimensions=384)
    client=QdrantClient(url="http://localhost:6333")
    collection=client.get_collection("spotify_memory_embeddings_test")
    assert collection.config.params.vectors.size==384
    store.close()
    client.close()