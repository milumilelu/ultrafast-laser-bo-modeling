"""Auditable literature ingestion and canonicalization."""

from ultrafast_memory.literature.service import (
    get_ingestion_status,
    ingest_literature,
    inventory_literature,
    plan_ingestion,
)

__all__ = [
    "get_ingestion_status",
    "ingest_literature",
    "inventory_literature",
    "plan_ingestion",
]
