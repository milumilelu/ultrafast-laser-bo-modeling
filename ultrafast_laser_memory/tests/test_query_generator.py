from __future__ import annotations

from ultrafast_memory.knowledge_bootstrap.query_generator import generate_search_queries


def test_query_generator_diamond_crl_templates():
    queries = generate_search_queries({"material": "diamond", "component_type": "CRL"}, "金刚石 CRL", "find_literature_prior")

    assert "diamond compound refractive lens femtosecond laser micromachining" in queries


def test_query_generator_general_ultrafast_templates():
    queries = generate_search_queries({"material": "AlSiC", "process_type": "cutting"}, None, "find_literature_prior")

    assert "AlSiC ultrafast laser cutting surface roughness" in queries
