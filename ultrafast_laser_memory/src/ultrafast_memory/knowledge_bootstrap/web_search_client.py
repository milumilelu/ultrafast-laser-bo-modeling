from __future__ import annotations


class BaseWebSearchClient:
    def search(self, queries: list[str], max_sources: int = 5) -> list[dict]:
        raise NotImplementedError


class MockWebSearchClient(BaseWebSearchClient):
    def search(self, queries: list[str], max_sources: int = 5) -> list[dict]:
        sources: list[dict] = []
        for query in queries:
            text = query.lower()
            if "diamond" in text and ("crl" in text or "lens" in text or "x-ray" in text):
                sources.append(
                    {
                        "title": "Mock: Femtosecond laser micromachining of diamond X-ray lenses",
                        "url": "https://example.org/mock-diamond-crl",
                        "snippet": (
                            "Femtosecond laser micromachining has been reported for single-crystal "
                            "diamond X-ray refractive lens fabrication. This supports feasibility but "
                            "not direct parameter transfer."
                        ),
                        "source_type": "paper",
                        "provider": "mock_web_search",
                        "published_at": None,
                    }
                )
            elif query.strip():
                sources.append(
                    {
                        "title": f"Mock: {query}",
                        "url": f"https://example.org/mock-search/{abs(hash(query))}",
                        "snippet": "Mock source for ultrafast laser background evidence. Expert review is required before use.",
                        "source_type": "web_page",
                        "provider": "mock_web_search",
                        "published_at": None,
                    }
                )
            if len(sources) >= max_sources:
                break
        return _dedupe(sources)[:max_sources]


class OpenAIWebSearchClient(BaseWebSearchClient):
    def search(self, queries: list[str], max_sources: int = 5) -> list[dict]:
        raise NotImplementedError("Real OpenAI web search is not implemented in MVP.")


def _dedupe(sources: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for source in sources:
        key = source.get("url") or source.get("title")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped
