from __future__ import annotations

import argparse
import json
import sys

from ultrafast_memory.app import launcher
from ultrafast_memory.demo.service import DemoService
from ultrafast_memory.doctor.service import DoctorService


COMMANDS = {"tui", "api", "doctor", "demo"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ultrafast",
        description="Formal entry for the ultrafast-laser Main Agent, demo, and diagnostics.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("tui", help="Start the PowerShell TUI")
    api = subparsers.add_parser("api", help="Start the FastAPI server")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    subparsers.add_parser("doctor", help="Run offline health diagnostics")
    demo = subparsers.add_parser("demo", help="Run deterministic offline demos")
    demo.add_argument("scenario", choices=["tgv"], default="tgv", nargs="?")
    demo.add_argument("--approve-review", action="store_true", help="Explicitly approve the demo task-scoped review card")
    demo.add_argument(
        "--trial-mode", choices=["simple_trial_cut", "full_trial_cut", "skip_trial"],
        help="Explicit trial strategy; omission returns the trial-mode review checkpoint.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--demo":
        args = ["demo", *args[1:]]
    if args in (["--help"], ["-h"]):
        _parser().print_help()
        return 0
    if not args or args[0] not in COMMANDS:
        return launcher.main(args)
    parsed = _parser().parse_args(args)
    if parsed.command == "tui":
        return launcher.main([])
    if parsed.command == "api":
        import uvicorn

        uvicorn.run("ultrafast_memory.apps.api.main:app", host=parsed.host, port=parsed.port, reload=False)
        return 0
    if parsed.command == "doctor":
        result = DoctorService().run()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "healthy" else 1
    if parsed.command == "demo":
        result = (
            DemoService().run_tgv(parsed.approve_review, selected_trial_mode=parsed.trial_mode)
            if parsed.trial_mode
            else DemoService().run_tgv(parsed.approve_review)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"completed", "waiting_review", "read_only_demo"} else 1
    _parser().print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
