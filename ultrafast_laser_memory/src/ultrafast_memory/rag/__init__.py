"""Hybrid retrieval over traceable literature chunks."""
__all__ = ["query_rag"]


def __getattr__(name: str):
    if name == "query_rag":
        from ultrafast_memory.rag.query_service import query_rag

        return query_rag
    raise AttributeError(name)
