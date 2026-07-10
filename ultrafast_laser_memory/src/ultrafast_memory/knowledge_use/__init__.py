__all__ = ["KnowledgeUseApplicationService"]


def __getattr__(name: str):
    if name == "KnowledgeUseApplicationService":
        from ultrafast_memory.knowledge_use.service import KnowledgeUseApplicationService

        return KnowledgeUseApplicationService
    raise AttributeError(name)
