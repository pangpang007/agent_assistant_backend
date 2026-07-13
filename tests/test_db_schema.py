from app.models.base import Base


EXPECTED_TABLES = {
    "users",
    "teams",
    "agents",
    "tools",
    "agent_tools",
    "agent_knowledge_bases",
    "knowledge_bases",
    "knowledge_documents",
    "knowledge_chunks",
    "model_providers",
    "llm_models",
    "model_usages",
    "workflows",
    "workflow_versions",
    "templates",
    "executions",
    "execution_nodes",
    "logs",
    "env_variables",
}


def test_all_tables_registered():
    import app.models  # noqa: F401

    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES
