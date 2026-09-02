CREATE CONSTRAINT subject_node_id_unique IF NOT EXISTS
FOR (n:Subject)
REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT memory_node_id_unique IF NOT EXISTS
FOR (n:Memory)
REQUIRE n.node_id IS UNIQUE;
CREATE CONSTRAINT memory_memory_id_unique IF NOT EXISTS
FOR (n:Memory)
REQUIRE n.memory_id IS UNIQUE;
CREATE CONSTRAINT entity_node_id_unique IF NOT EXISTS
FOR (n:Entity)
REQUIRE n.node_id IS UNIQUE;
CREATE INDEX memory_subject_id_index IF NOT EXISTS
FOR (n:Memory)
ON (n.subject_id);
CREATE INDEX memory_status_index IF NOT EXISTS
FOR (n:Memory)
ON (n.status);
CREATE INDEX memory_valid_from_index IF NOT EXISTS
FOR (n:Memory)
ON (n.valid_from);
CREATE INDEX memory_valid_to_index IF NOT EXISTS
FOR (n:Memory)
ON (n.valid_to);
CREATE INDEX entity_canonical_id_index IF NOT EXISTS
FOR (n:Entity)
ON (n.canonical_id);