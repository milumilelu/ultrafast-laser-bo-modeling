__all__ = ["TrialApplicationService", "TrialClosedLoopService"]


def __getattr__(name: str):
    if name == "TrialApplicationService":
        from ultrafast_memory.trial.service import TrialApplicationService

        return TrialApplicationService
    if name == "TrialClosedLoopService":
        from ultrafast_memory.trial.closed_loop import TrialClosedLoopService

        return TrialClosedLoopService
    raise AttributeError(name)
