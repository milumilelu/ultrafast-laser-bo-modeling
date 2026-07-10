"""Auditable literature ingestion and canonicalization."""

__all__ = [
    "get_ingestion_status",
    "ingest_literature",
    "inventory_literature",
    "plan_ingestion",
]


def __getattr__(name: str):
    if name in __all__:
        from ultrafast_memory.literature import service

        return getattr(service, name)
    raise AttributeError(name)
