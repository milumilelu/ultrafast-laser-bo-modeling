# Current Git state

Snapshot target: `cb5094903bb83489bb278f34ae7005973cc21ded` (`cb50949 Add auditable agent workflows and literature RAG`).

## Repository identity

| Item | Observed value |
|---|---|
| Repository root | `<REPOSITORY_ROOT>` |
| Remote | `origin` → `https://github.com/milumilelu/ultrafast-laser-bo-modeling.git` |
| Current branch | `main` |
| Upstream | `origin/main` |
| HEAD | `cb5094903bb83489bb278f34ae7005973cc21ded` |
| Local branches | `main` only |
| Remote branches | `origin/main`; `origin/HEAD -> origin/main` |
| Baseline tag | local annotated tag `pre-agent-refactor`, resolving to HEAD |

`git fetch --all --prune` completed before this snapshot. Local `main` and `origin/main` point to the same commit.

## Working tree

No tracked modification or deletion was present when Phase 0 began. The tree was not clean because it already contained untracked user assets, including the master task document, `agent_skills/`, task-state outputs, Chinese technical diagrams/documents, and other project material.

Phase 0 adds only untracked analysis artifacts under `docs/`, `reports/`, and `scripts/`. Existing untracked files were not edited, moved, staged, or deleted. The machine-readable path-level snapshot is in `reports/repository_inventory.json`.

## Key ignored paths

| Path | Reason / observation |
|---|---|
| `ultrafast_laser_memory/data/**` | Live SQLite database, RAG data, exports, archives, and local baseline backup |
| `ultrafast_laser_memory/超快智能体文献检索/**` | Source PDFs and generated literature deliverables |
| `ultrafast_laser_memory/configs/llm.local.json` | Local provider configuration |
| `ultrafast_laser_memory/configs/secrets/` | DPAPI-protected secret material |
| `.pytest_cache/`, `.ruff_cache/`, `__pycache__/` | Local caches |
| `outputs/run_log.txt` and UI logs | Local runtime logs |

No API-key or DPAPI content was read into a report. Reports record only existence, size, ignore status, and backup policy.

## Multiple project roots

Two executable project roots share one Git repository:

1. Repository root: legacy modeling and interactive BO (`main.py`, `src/`, `tests/`, `requirements.txt`).
2. `ultrafast_laser_memory/`: packaged agent/memory application (`pyproject.toml`, FastAPI, Typer CLI, PowerShell TUI, SQLite/RAG, and its own tests).

This is a real architectural split, not merely two folders: the agent-side BO adapter is not connected to the legacy BO implementation.

## Baseline freeze

- Local tag: `pre-agent-refactor`.
- SQLite online backup: `ultrafast_laser_memory/data/backups/pre-agent-refactor/cb5094903bb8/` (ignored by Git).
- Default and local non-secret LLM configuration backed up in the same ignored directory.
- DPAPI/API-key material intentionally excluded from the copied configuration backup.
- Test, CLI, API golden, replay, and performance records are stored under `reports/`.

The tag has not been pushed. Phase 0 does not authorize a remote push or later-phase refactor.
