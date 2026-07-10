from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "ultrafast_laser_memory"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sqlite_summary(path: Path) -> dict:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
        return {
            "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "tables": {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for (table,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = (
        Path(args.output).resolve()
        if args.output
        else (PROJECT / "data/backups/refactor" / timestamp).resolve()
    )
    allowed_root = (PROJECT / "data/backups").resolve()
    if destination != allowed_root and allowed_root not in destination.parents:
        raise ValueError(f"backup destination must stay under {allowed_root}")
    database_dir = destination / "database"
    config_dir = destination / "configs"
    git_dir = destination / "git"
    for path in (database_dir, config_dir, git_dir):
        path.mkdir(parents=True, exist_ok=True)

    source_db = PROJECT / "data/ultrafast_memory.db"
    backup_db = database_dir / source_db.name
    with sqlite3.connect(source_db) as source, sqlite3.connect(backup_db) as target:
        source.backup(target)

    configs = []
    for source in (
        PROJECT / "configs/default.yaml",
        PROJECT / "configs/local.yaml",
        PROJECT / "configs/llm.local.json",
    ):
        if source.exists():
            target = config_dir / source.name
            shutil.copy2(source, target)
            configs.append({"source": str(source), "backup": str(target), "sha256": sha256(target)})

    git_records = {}
    for name, command in {
        "head": ["git", "rev-parse", "HEAD"],
        "branch": ["git", "branch", "--show-current"],
        "status": ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        "diff": ["git", "diff", "--binary"],
        "diff_cached": ["git", "diff", "--cached", "--binary"],
    }.items():
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
        )
        path = git_dir / f"{name}.txt"
        path.write_text(completed.stdout, encoding="utf-8")
        git_records[name] = str(path)

    source_summary = sqlite_summary(source_db)
    backup_summary = sqlite_summary(backup_db)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(ROOT),
        "backup_root": str(destination),
        "database": {
            "source": str(source_db),
            "backup": str(backup_db),
            "source_sha256": sha256(source_db),
            "backup_sha256": sha256(backup_db),
            "logical_snapshot_matches": source_summary == backup_summary,
            "source_summary": source_summary,
            "backup_summary": backup_summary,
        },
        "configs": configs,
        "git": git_records,
        "secret_store_copied": False,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"backup_root": str(destination), "manifest": str(manifest_path), "logical_snapshot_matches": manifest["database"]["logical_snapshot_matches"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
