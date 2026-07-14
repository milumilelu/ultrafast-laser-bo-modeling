from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
import time

import pytest

from ultrafast_agent.runtime.events import AgentEvent
from ultrafast_integrations.storage.runtime_event_repository import RuntimeEventRepository
from ultrafast_memory.agent_runtime.trace_collector import record_agent_trace_event
from ultrafast_memory.db.init_db import init_database
from ultrafast_memory.db.session import get_connection


def _event(stream_id: str, marker: str, idempotency_key: str | None = None) -> AgentEvent:
    return AgentEvent(
        run_id=stream_id,
        sequence=0,
        event_type="concurrency_probe",
        stage="runtime",
        title="并发写入",
        summary=marker,
        status="completed",
        idempotency_key=idempotency_key,
    )


def _process_writer(args: tuple[str, str, int, int, str | None]) -> list[tuple[str, int]]:
    db_path, stream_id, worker_id, count, shared_key = args
    repository = RuntimeEventRepository(db_path)
    values = []
    for index in range(count):
        event = _event(
            stream_id,
            f"worker={worker_id};index={index}",
            shared_key,
        )
        repository.persist(event)
        values.append((event.event_id, event.sequence))
    return values


def _crash_with_open_sequence_transaction(db_path: str, stream_id: str) -> None:
    with get_connection(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        RuntimeEventRepository._allocate_sequence(connection, stream_id)
        os._exit(7)


def test_sequence_is_unique_across_eight_processes(isolated_root):
    db_path = init_database()
    context = multiprocessing.get_context("spawn")
    work = [(str(db_path), "multiprocess-stream", worker, 100, None) for worker in range(8)]
    with context.Pool(processes=8) as pool:
        written = pool.map(_process_writer, work)

    flat = [item for batch in written for item in batch]
    records = RuntimeEventRepository(db_path).list_run_events("multiprocess-stream")
    sequences = [item["sequence"] for item in records]
    assert len(flat) == len(records) == 800
    assert len({event_id for event_id, _ in flat}) == 800
    assert sequences == list(range(1, 801))
    with get_connection(db_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_sequence_is_unique_across_threads(isolated_root):
    db_path = init_database()
    repository = RuntimeEventRepository(db_path)

    def write(index: int) -> int:
        event = _event("thread-stream", str(index))
        repository.persist(event)
        return event.sequence

    with ThreadPoolExecutor(max_workers=8) as executor:
        sequences = list(executor.map(write, range(200)))
    assert sorted(sequences) == list(range(1, 201))


def test_duplicate_idempotency_key_is_one_canonical_event_across_processes(isolated_root):
    db_path = init_database()
    context = multiprocessing.get_context("spawn")
    work = [(str(db_path), "retry-stream", worker, 1, "request-42") for worker in range(8)]
    with context.Pool(processes=8) as pool:
        written = pool.map(_process_writer, work)

    flat = [item for batch in written for item in batch]
    records = RuntimeEventRepository(db_path).list_run_events("retry-stream")
    assert len(records) == 1
    assert records[0]["sequence"] == 1
    assert len({event_id for event_id, _ in flat}) == 1


def test_legacy_api_exposes_idempotent_canonical_write(isolated_root):
    first = record_agent_trace_event(
        "idempotent-session",
        "tool_result",
        "结果",
        "第一次结果",
        idempotency_key="tool-call-9:result",
    )
    second = record_agent_trace_event(
        "idempotent-session",
        "tool_result",
        "被忽略的重复结果",
        "重试载荷不得覆盖第一次结果",
        idempotency_key="tool-call-9:result",
    )
    assert first["event_id"] == second["event_id"]
    assert first["sequence"] == second["sequence"] == 1
    assert second["summary"] == "第一次结果"


def test_insert_failure_rolls_back_allocated_sequence(isolated_root, monkeypatch):
    db_path = init_database()
    repository = RuntimeEventRepository(db_path)

    def fail_insert(*args, **kwargs):
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(repository, "_insert_event", fail_insert)
    with pytest.raises(RuntimeError, match="simulated insert failure"):
        repository.persist(_event("rollback-stream", "failed"))

    event = _event("rollback-stream", "success")
    RuntimeEventRepository(db_path).persist(event)
    assert event.sequence == 1


def test_worker_crash_rolls_back_sequence_counter(isolated_root):
    db_path = init_database()
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_crash_with_open_sequence_transaction,
        args=(str(db_path), "crash-stream"),
    )
    process.start()
    process.join(timeout=20)
    assert process.exitcode == 7

    event = _event("crash-stream", "after-crash")
    RuntimeEventRepository(db_path).persist(event)
    assert event.sequence == 1


def test_sqlite_busy_waits_then_commits_without_lost_event(isolated_root):
    db_path = init_database()
    blocker = get_connection(db_path)
    blocker.execute("BEGIN IMMEDIATE")
    repository = RuntimeEventRepository(db_path)
    event = _event("busy-stream", "waited")
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(repository.persist, event)
            time.sleep(0.2)
            assert not future.done()
            blocker.commit()
            future.result(timeout=10)
    finally:
        blocker.close()
    assert event.sequence == 1
