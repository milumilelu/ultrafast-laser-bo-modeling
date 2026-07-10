"""Compatibility facade used by the legacy CLI.

The public functions intentionally preserve the original signatures and payloads.
"""

from __future__ import annotations

import sys
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_AGENT_SRC = _REPOSITORY_ROOT / "ultrafast_laser_memory/src"
if str(_AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENT_SRC))

from ultrafast_bo.compatibility.legacy_commands import (  # noqa: E402
    LegacyCommandCompatibilityService,
    LegacyCommandDelegates,
)
from src.interactive_bo import (  # noqa: E402
    export_task_logs as _export_task_logs,
    feedback_json as _feedback_json,
    init_task as _init_task,
    load_task_state as _load_task_state,
    recommend_next as _recommend_next,
    recommend_parameters as _recommend_parameters,
    run_json as _run_json,
    save_task_state as _save_task_state,
    submit_feedback as _submit_feedback,
)


_SERVICE = LegacyCommandCompatibilityService(
    LegacyCommandDelegates(
        init_task=_init_task,
        load_task_state=_load_task_state,
        save_task_state=_save_task_state,
        recommend_parameters=_recommend_parameters,
        submit_feedback=_submit_feedback,
        recommend_next=_recommend_next,
        export_task_logs=_export_task_logs,
        run_json=_run_json,
        feedback_json=_feedback_json,
    )
)


init_task = _SERVICE.init_task
load_task_state = _SERVICE.load_task_state
save_task_state = _SERVICE.save_task_state
recommend_parameters = _SERVICE.recommend_parameters
submit_feedback = _SERVICE.submit_feedback
recommend_next = _SERVICE.recommend_next
export_task_logs = _SERVICE.export_task_logs
run_json = _SERVICE.run_json
feedback_json = _SERVICE.feedback_json
