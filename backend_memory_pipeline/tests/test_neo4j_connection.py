import os
from backend_memory_pipeline.persistence.neo4j.graph_store import Neo4jGraphStore
def test_neo4j_connectivity():
    store=Neo4jGraphStore(
        uri=os.getenv("NEO4J_URI","bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME","neo4j"),
        password=os.getenv("NEO4J_PASSWORD","password"),
        database=os.getenv("NEO4J_DATABASE","neo4j"),
    )
    try:
        store.verify_connectivity()
    finally:
        store.close()