from __future__ import annotations

import sqlite3
from pathlib import Path


def _read_single_value(db_path: Path, sql: str):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(sql).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def _sample_message(**overrides):
    base = {
        "source_table": "message_table",
        "source_rowid": 12,
        "conversation_id": "S:100_200",
        "conversation_name": "Customer A",
        "conversation_type": "direct",
        "message_id": 101,
        "server_id": 0,
        "sequence": 5,
        "send_time": 1_718_000_000,
        "sender_id": "200",
        "sender_name": "Customer A",
        "content": "Hello",
        "content_summary": "Hello",
    }
    base.update(overrides)
    return base


def test_build_message_key_is_stable_when_content_changes():
    import wxwork_message_monitor as monitor

    first_key, first_event = monitor.build_message_key(_sample_message())
    second_key, second_event = monitor.build_message_key(
        _sample_message(content="Different body", content_summary="Different body")
    )

    assert first_key == second_key
    assert first_event == second_event


def test_build_message_key_is_stable_when_sequence_changes_for_same_row():
    import wxwork_message_monitor as monitor

    first_key, first_event = monitor.build_message_key(_sample_message(sequence=5, source_rowid=12, message_id=101))
    second_key, second_event = monitor.build_message_key(
        _sample_message(sequence=99, source_rowid=12, message_id=101)
    )

    assert first_key == second_key
    assert first_event == second_event


def test_snapshots_changed_detects_size_and_mtime_changes(tmp_path):
    import wxwork_message_monitor as monitor

    db_file = tmp_path / "message.db"
    db_file.write_text("a", encoding="utf-8")
    first = monitor.snapshot_files(str(tmp_path))
    db_file.write_text("ab", encoding="utf-8")
    second = monitor.snapshot_files(str(tmp_path))

    assert monitor.snapshots_changed(first, second) is True


def test_monitor_state_store_deduplicates_seen_messages(tmp_path):
    import wxwork_message_monitor as monitor

    db_path = tmp_path / "monitor_state.db"
    store = monitor.MonitorStateStore(str(db_path))
    accepted = store.record_seen_and_enqueue("evt-1", "wxwork:key-1", {"event_id": "evt-1"})
    duplicate = store.record_seen_and_enqueue("evt-1", "wxwork:key-1", {"event_id": "evt-1"})

    assert accepted is True
    assert duplicate is False
    assert _read_single_value(db_path, "SELECT COUNT(*) FROM seen_messages") == 1
    assert _read_single_value(db_path, "SELECT COUNT(*) FROM outbox") == 1


def test_perform_warmup_marks_seen_without_enqueueing_history(monkeypatch, tmp_path):
    import wxwork_message_monitor as monitor

    db_path = tmp_path / "monitor_state.db"
    store = monitor.MonitorStateStore(str(db_path))
    monkeypatch.setattr(monitor, "refresh_decrypted_cache", lambda _runtime_dir: {"ok": True})
    monkeypatch.setattr(
        monitor.wxwork_query,
        "get_messages_for_monitor",
        lambda limit=2000: [_sample_message(message_id=201), _sample_message(message_id=202, sequence=6)],
    )

    monitor.perform_warmup(store, str(tmp_path), 2000)

    assert store.get_state("warmup_completed") == "true"
    assert _read_single_value(db_path, "SELECT COUNT(*) FROM seen_messages") == 2
    assert _read_single_value(db_path, "SELECT COUNT(*) FROM outbox") == 0


def test_deliver_outbox_retries_then_marks_delivered(monkeypatch, tmp_path):
    import wxwork_message_monitor as monitor
    import json

    db_path = tmp_path / "monitor_state.db"
    token_file = tmp_path / "token.txt"
    token_file.write_text("token", encoding="utf-8")
    store = monitor.MonitorStateStore(str(db_path))
    store.record_seen_and_enqueue("evt-1", "wxwork:key-1", {"event_id": "evt-1"})

    outcomes = iter(
        [
            (False, "HTTP 500"),
            (
                True,
                "accepted",
                {
                    "langbot_ingested_at": "2026-06-24T10:00:00.100000+00:00",
                    "sse_published_at": "2026-06-24T10:00:00.200000+00:00",
                },
            ),
        ]
    )
    monkeypatch.setattr(monitor, "push_event", lambda *_args, **_kwargs: next(outcomes))

    monitor.deliver_outbox(store, "http://127.0.0.1:5300/api/v1/local-connectors/internal/events", str(token_file))
    attempt_count = _read_single_value(db_path, "SELECT attempt_count FROM outbox WHERE event_id = 'evt-1'")
    status = _read_single_value(db_path, "SELECT status FROM outbox WHERE event_id = 'evt-1'")

    assert attempt_count == 1
    assert status == monitor.OUTBOX_STATUS_PENDING

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE outbox SET next_attempt_at = 0 WHERE event_id = 'evt-1'")
        conn.commit()
    finally:
        conn.close()

    monitor.deliver_outbox(store, "http://127.0.0.1:5300/api/v1/local-connectors/internal/events", str(token_file))
    delivered_status = _read_single_value(db_path, "SELECT status FROM outbox WHERE event_id = 'evt-1'")
    payload_json = _read_single_value(db_path, "SELECT payload_json FROM outbox WHERE event_id = 'evt-1'")
    stored_payload = json.loads(payload_json)

    assert delivered_status == monitor.OUTBOX_STATUS_DELIVERED
    assert stored_payload["timings"]["langbot_ingested_at"] == "2026-06-24T10:00:00.100000+00:00"
    assert stored_payload["timings"]["sse_published_at"] == "2026-06-24T10:00:00.200000+00:00"


def test_wait_for_stable_snapshot_requires_two_identical_checks(monkeypatch):
    import wxwork_message_monitor as monitor

    changed = {name: {"exists": 1, "size": 10, "mtime_ns": 10} for name in monitor.MONITORED_FILES}
    still_changing = {name: {"exists": 1, "size": 20, "mtime_ns": 20} for name in monitor.MONITORED_FILES}
    stable = {name: {"exists": 1, "size": 30, "mtime_ns": 30} for name in monitor.MONITORED_FILES}
    snapshots = iter([still_changing, stable, stable])
    sleeps: list[float] = []

    monkeypatch.setattr(monitor, "snapshot_files", lambda _db_dir: next(snapshots))
    monkeypatch.setattr(monitor.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = monitor.wait_for_stable_snapshot(
        "C:\\fake-db",
        changed,
        stability_checks=2,
        stability_interval_ms=250,
        max_stability_wait_ms=1_000,
    )

    assert result["snapshot"] == stable
    assert result["stable"] is True
    assert sleeps == [0.25, 0.25, 0.25]


def test_wait_for_stable_snapshot_accepts_initial_snapshot_when_already_stable(monkeypatch):
    import wxwork_message_monitor as monitor

    changed = {name: {"exists": 1, "size": 10, "mtime_ns": 10} for name in monitor.MONITORED_FILES}
    snapshots = iter([changed, changed])
    sleeps: list[float] = []

    monkeypatch.setattr(monitor, "snapshot_files", lambda _db_dir: next(snapshots))
    monkeypatch.setattr(monitor.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = monitor.wait_for_stable_snapshot(
        "C:\\fake-db",
        changed,
        stability_checks=2,
        stability_interval_ms=250,
        max_stability_wait_ms=1_000,
    )

    assert result["snapshot"] == changed
    assert result["stable"] is True
    assert sleeps == [0.25, 0.25]


def test_wait_for_stable_snapshot_stops_at_max_wait(monkeypatch):
    import wxwork_message_monitor as monitor

    base = {name: {"exists": 1, "size": 1, "mtime_ns": 1} for name in monitor.MONITORED_FILES}
    snapshots = iter(
        [
            {name: {"exists": 1, "size": 2, "mtime_ns": 2} for name in monitor.MONITORED_FILES},
            {name: {"exists": 1, "size": 3, "mtime_ns": 3} for name in monitor.MONITORED_FILES},
            {name: {"exists": 1, "size": 4, "mtime_ns": 4} for name in monitor.MONITORED_FILES},
            {name: {"exists": 1, "size": 5, "mtime_ns": 5} for name in monitor.MONITORED_FILES},
        ]
    )
    time_values = iter([0.0, 0.25, 0.50, 0.75, 1.0, 1.25])

    monkeypatch.setattr(monitor, "snapshot_files", lambda _db_dir: next(snapshots))
    monkeypatch.setattr(monitor.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(monitor.time, "monotonic", lambda: next(time_values))

    result = monitor.wait_for_stable_snapshot(
        "C:\\fake-db",
        base,
        stability_checks=2,
        stability_interval_ms=250,
        max_stability_wait_ms=1_000,
    )

    assert result["snapshot"] == {name: {"exists": 1, "size": 5, "mtime_ns": 5} for name in monitor.MONITORED_FILES}
    assert result["stable"] is False


def test_determine_refresh_targets_only_includes_changed_databases():
    import wxwork_message_monitor as monitor

    previous = {name: {"exists": 1, "size": 1, "mtime_ns": 1} for name in monitor.MONITORED_FILES}
    current = {name: {"exists": 1, "size": 1, "mtime_ns": 1} for name in monitor.MONITORED_FILES}
    current["message.db"]["mtime_ns"] = 2
    current["message.db-wal"]["mtime_ns"] = 2
    current["user.db"]["mtime_ns"] = 2

    assert monitor.determine_refresh_targets(previous, current) == ["message.db", "user.db"]


def test_scan_and_enqueue_passes_incremental_cursor_and_refresh_targets(monkeypatch, tmp_path):
    import wxwork_message_monitor as monitor

    db_path = tmp_path / "monitor_state.db"
    store = monitor.MonitorStateStore(str(db_path))
    store.set_state("monitor_cursor", '{"send_time":300,"sequence":3,"message_id":30,"source_rowid":3,"source_table":"message_table"}')
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        monitor,
        "refresh_decrypted_cache",
        lambda _runtime_dir, database_list=None: (
            captured.setdefault("refresh_targets", database_list),
            {"ok": True},
        )[1],
    )

    def fake_get_messages_for_monitor(*, limit=2000, after_cursor=None, lookback_seconds=120):
        captured["limit"] = limit
        captured["after_cursor"] = after_cursor
        captured["lookback_seconds"] = lookback_seconds
        return [_sample_message(message_id=301, sequence=7, send_time=1_718_000_100, source_rowid=77)]

    monkeypatch.setattr(monitor.wxwork_query, "get_messages_for_monitor", fake_get_messages_for_monitor)

    result = monitor.scan_and_enqueue(
        store,
        str(tmp_path),
        2_000,
        refresh_targets=["message.db"],
    )

    assert captured["refresh_targets"] == ["message.db"]
    assert captured["after_cursor"] == {
        "send_time": 300,
        "message_id": 30,
        "source_rowid": 3,
        "source_table": "message_table",
        "sequence": 3,
    }
    assert result["new_messages"] == 1
    assert _read_single_value(db_path, "SELECT COUNT(*) FROM outbox") == 1


def test_record_seen_and_enqueue_sets_outbox_created_timestamp(tmp_path):
    import json
    import wxwork_message_monitor as monitor

    db_path = tmp_path / "monitor_state.db"
    store = monitor.MonitorStateStore(str(db_path))
    payload = {"event_id": "evt-9", "message_key": "wxwork:key-9", "timings": {}}

    accepted = store.record_seen_and_enqueue("evt-9", "wxwork:key-9", payload)

    assert accepted is True
    stored_payload = _read_single_value(
        db_path,
        "SELECT payload_json FROM outbox WHERE event_id = 'evt-9'",
    )
    decoded = json.loads(stored_payload)
    assert decoded["timings"]["outbox_created_at"]


def test_adaptive_poll_controller_uses_active_then_idle_backoff():
    import wxwork_message_monitor as monitor

    controller = monitor.AdaptivePollController()

    assert controller.current_interval_ms == 500

    controller.record_result(had_activity=False, had_error=False)
    assert controller.current_interval_ms == 1_000

    controller.record_result(had_activity=False, had_error=False)
    assert controller.current_interval_ms == 2_000

    controller.record_result(had_activity=False, had_error=False)
    assert controller.current_interval_ms == 2_000


def test_adaptive_poll_controller_resets_to_active_after_new_messages():
    import wxwork_message_monitor as monitor

    controller = monitor.AdaptivePollController()
    controller.record_result(had_activity=False, had_error=False)
    controller.record_result(had_activity=False, had_error=False)

    assert controller.current_interval_ms == 2_000

    controller.record_result(had_activity=True, had_error=False)

    assert controller.current_interval_ms == 500


def test_run_with_sqlite_retry_uses_short_locked_backoff(monkeypatch):
    import wxwork_message_monitor as monitor

    attempts = {"count": 0}
    sleeps: list[float] = []

    def flaky_operation():
        attempts["count"] += 1
        if attempts["count"] <= 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    monkeypatch.setattr(monitor.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = monitor.run_with_sqlite_retry(flaky_operation)

    assert result == "ok"
    assert attempts["count"] == 4
    assert sleeps == [0.05, 0.1, 0.2]


def test_is_source_refresh_stale_when_missing_or_expired():
    import wxwork_message_monitor as monitor

    assert monitor.is_source_refresh_stale(None) is True
    assert (
        monitor.is_source_refresh_stale(
            "2026-06-25T02:00:00",
            now_at="2026-06-25T02:00:01.999000",
        )
        is False
    )
    assert (
        monitor.is_source_refresh_stale(
            "2026-06-25T02:00:00",
            now_at="2026-06-25T02:00:02.001000",
        )
        is True
    )


def test_run_refresh_cycle_retries_once_after_empty_scan(monkeypatch, tmp_path):
    import wxwork_message_monitor as monitor

    db_path = tmp_path / "monitor_state.db"
    store = monitor.MonitorStateStore(str(db_path))
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_scan_and_enqueue(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "new_messages": 0,
                "scanned_messages": 3,
                "latest_cursor": None,
                "decrypt_started_at": "first-start",
                "decrypt_completed_at": "first-done",
                "scan_completed_at": "first-scan",
            }
        return {
            "new_messages": 1,
            "scanned_messages": 1,
            "latest_cursor": {"message_id": 1},
            "decrypt_started_at": "second-start",
            "decrypt_completed_at": "second-done",
            "scan_completed_at": "second-scan",
        }

    monkeypatch.setattr(monitor, "scan_and_enqueue", fake_scan_and_enqueue)
    monkeypatch.setattr(monitor.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = monitor.run_refresh_cycle(
        store,
        str(tmp_path),
        2_000,
        refresh_targets=["message.db"],
        confirmation_delay_ms=100,
    )

    assert calls["count"] == 2
    assert sleeps == [0.1]
    assert result["new_messages"] == 1
    assert result["scanned_messages"] == 4
    assert result["latest_cursor"] == {"message_id": 1}


def test_scan_and_enqueue_keeps_multiple_same_second_messages(monkeypatch, tmp_path):
    import wxwork_message_monitor as monitor

    db_path = tmp_path / "monitor_state.db"
    store = monitor.MonitorStateStore(str(db_path))
    scanned_messages = [
        _sample_message(message_id=401, send_time=1_718_000_200, sequence=11, source_rowid=101),
        _sample_message(message_id=402, send_time=1_718_000_200, sequence=12, source_rowid=102),
    ]

    monkeypatch.setattr(
        monitor,
        "refresh_decrypted_cache",
        lambda _runtime_dir, database_list=None: {"ok": True},
    )
    monkeypatch.setattr(
        monitor.wxwork_query,
        "get_messages_for_monitor",
        lambda **_kwargs: scanned_messages,
    )

    result = monitor.scan_and_enqueue(store, str(tmp_path), 2_000, refresh_targets=["message.db"])

    assert result["new_messages"] == 2
    assert _read_single_value(db_path, "SELECT COUNT(*) FROM outbox") == 2
    assert _read_single_value(db_path, "SELECT COUNT(*) FROM seen_messages") == 2
