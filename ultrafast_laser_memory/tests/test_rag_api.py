from fastapi.testclient import TestClient

from ultrafast_memory.app.api import app
from ultrafast_memory.db.init_db import init_database


def test_literature_and_rag_api(isolated_root, mixed_literature_root):
    init_database()
    client = TestClient(app)
    inventory = client.post("/literature/inventory", json={"root": str(mixed_literature_root)})
    assert inventory.status_code == 200
    assert inventory.json()["asset_counts"]["raw_pdf"] == 1
    ingestion = client.post("/literature/ingest", json={"root": str(mixed_literature_root)})
    assert ingestion.status_code == 200
    created = client.post("/rag/indexes", json={"index_name": "literature_default"})
    assert created.status_code == 200
    index_id = created.json()["index_id"]
    assert client.post(f"/rag/indexes/{index_id}/index", json={}).json()["indexed_count"] > 0
    query = client.post("/rag/query", json={"query": "TGV taper crack", "filters": {"material": "glass_wafer"}})
    assert query.status_code == 200
    assert query.json()["hits"]
