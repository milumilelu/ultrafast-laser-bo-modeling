from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ultrafast_agent.task_intake.replay import evaluate_replay, load_replay_cases  # noqa: E402
from ultrafast_memory.core.llm_config import get_llm_config  # noqa: E402
from ultrafast_memory.llm.factory import create_llm_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Task Intake against the replay corpus")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "tests" / "replay" / "process_task_cases.jsonl",
    )
    parser.add_argument("--live", action="store_true", help="Use the configured live LLM")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    cases = load_replay_cases(args.corpus)
    if args.limit is not None:
        cases = cases[: args.limit]
    factory = None
    if args.live:
        live_client = create_llm_client(get_llm_config())
        if getattr(live_client, "provider", None) == "mock":
            print(json.dumps({
                "status": "live_unavailable",
                "reason": "configured_provider_is_mock",
                "case_count": len(cases),
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 2
        def factory(_):
            return live_client
    report = evaluate_replay(cases, factory)
    report.pop("results", None)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
