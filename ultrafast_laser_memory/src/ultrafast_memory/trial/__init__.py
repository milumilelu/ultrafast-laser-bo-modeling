__all__ = ["TrialApplicationService"]


def __getattr__(name: str):
    if name == "TrialApplicationService":
        from ultrafast_memory.trial.service import TrialApplicationService

        return TrialApplicationService
    raise AttributeError(name)
