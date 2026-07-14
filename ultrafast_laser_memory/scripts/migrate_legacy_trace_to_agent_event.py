from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ultrafast_memory.migrations.legacy_trace import migrate_legacy_traces  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill legacy Trace rows into AgentEvent")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    report = migrate_legacy_traces(
        args.database,
        dry_run=args.dry_run,
        limit=args.limit,
        resume=args.resume,
        verify=args.verify,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not report["conflicts"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
