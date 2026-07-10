__all__ = ["TaskReportService"]


def __getattr__(name: str):
    if name == "TaskReportService":
        from ultrafast_memory.reports.task_report_service import TaskReportService

        return TaskReportService
    raise AttributeError(name)
