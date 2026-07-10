from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    cli_commands = {
        "init-db", "scan", "list-artifacts", "list-runs", "list-candidates",
        "review-candidate", "export-bo", "literature", "rag",
    }
    if raw_args and raw_args[0] in cli_commands:
        from ultrafast_memory.app.cli import app

        app(args=raw_args, prog_name="ultrafast", standalone_mode=True)
        return 0
    parser = argparse.ArgumentParser(prog="ultrafast", description="Start the Ultrafast Laser Agent PowerShell TUI.")
    parser.add_argument("--no-save", action="store_true", help="Do not save local LLM config or encrypted API key.")
    parser.add_argument("--skip-llm-config", action="store_true", help="Skip DeepSeek config and use MockLLM.")
    parser.add_argument("--show-menu", action="store_true", help="Open the manual launcher menu.")
    parser.add_argument("--reconfigure", action="store_true", help="Force DeepSeek model/API key setup.")
    parser.add_argument("--force-initialize", action="store_true", help="Force example scan and BO export.")
    args = parser.parse_args(raw_args)

    pwsh = shutil.which("pwsh")
    if not pwsh:
        print("PowerShell 7 (pwsh) is required for the ultrafast launcher.", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "start_agent_tui.ps1"
    if not script.exists():
        print(f"Launcher script not found: {script}", file=sys.stderr)
        return 1

    command = [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    if args.no_save:
        command.append("-NoSave")
    if args.skip_llm_config:
        command.append("-SkipLlmConfig")
    if args.show_menu:
        command.append("-ShowMenu")
    if args.reconfigure:
        command.append("-Reconfigure")
    if args.force_initialize:
        command.append("-ForceInitialize")
    return subprocess.call(command, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
