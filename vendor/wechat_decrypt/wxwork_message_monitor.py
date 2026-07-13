from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

import connector_runtime
import wxwork_query


MONITORED_FILES = (
    "message.db",
    "message.db-wal",
    "message.db-shm",
    "session.db",
    "session.db-wal",
    "session.db-shm",
    "user.db",
    "user.db-wal",
)

DEFAULT_POLL_SECONDS = 1
ACTIVE_POLL_INTERVAL_MS = 500
FIRST_IDLE_POLL_INTERVAL_MS = 1000
MAX_IDLE_POLL_INTERVAL_MS = 2000
DEFAULT_DEBOUNCE_MS = 0
DEFAULT_SCAN_LIMIT = 2000
DEFAULT_STABILITY_CHECKS = 2
DEFAULT_STABILITY_INTERVAL_MS = 250
DEFAULT_MAX_STABILITY_WAIT_MS = 1000
DEFAULT_MONITOR_LOOKBACK_SECONDS = 120
MAX_SOURCE_STALENESS_MS = 2000
POST_CHANGE_CONFIRMATION_DELAY_MS = 100
SQLITE_LOCK_RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2)
MAX_SEEN_MESSAGES = 10000
OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_DELIVERED = "delivered"
REFRESH_TARGET_MESSAGE = "message.db"
REFRESH_TARGET_SESSION = "session.db"
REFRESH_TARGET_USER = "user.db"
STALE_REFRESH_TARGETS = (
    REFRESH_TARGET_MESSAGE,
    REFRESH_TARGET_SESSION,
    REFRESH_TARGET_USER,
)
TIMING_FIELDS = (
    "file_change_detected_at",
    "stability_completed_at",
    "decrypt_started_at",
    "decrypt_completed_at",
    "scan_completed_at",
    "outbox_created_at",
    "delivery_succeeded_at",
    "langbot_ingested_at",
    "sse_published_at",
)


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat()


def monotonic_seconds() -> float:
    return time.monotonic()


def sent_time_to_iso(send_time: int) -> str:
    if send_time <= 0:
        return utcnow_iso()
    if send_time > 20_000_000_000:
        send_time = int(send_time / 1000)
    return datetime.datetime.fromtimestamp(send_time, datetime.timezone.utc).replace(tzinfo=None).isoformat()


def iso_to_datetime(value: str | None) -> datetime.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def duration_ms(started_at: str | None, completed_at: str | None) -> int | None:
    started = iso_to_datetime(started_at)
    completed = iso_to_datetime(completed_at)
    if started is None or completed is None:
        return None
    return max(0, int((completed - started).total_seconds() * 1000))


def hash_prefix(value: str, length: int = 12) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:length]


def is_sqlite_locked_error(exc: sqlite3.Error) -> bool:
    message = str(exc).strip().lower()
    return "locked" in message or "busy" in message


def run_with_sqlite_retry(operation):
    for delay_seconds in SQLITE_LOCK_RETRY_DELAYS_SECONDS:
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if not is_sqlite_locked_error(exc):
                raise
            time.sleep(delay_seconds)
    return operation()


def compact_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def summarize_snapshot_changes(
    previous: dict[str, dict[str, int]],
    current: dict[str, dict[str, int]],
) -> tuple[list[str], int, int]:
    changed_files: list[str] = []
    source_db_count = 0
    source_bytes = 0
    for file_name in MONITORED_FILES:
        snapshot = current.get(file_name) or {"exists": 0, "size": 0, "mtime_ns": 0}
        if file_name.endswith(".db") and int(snapshot.get("exists", 0)):
            source_db_count += 1
        source_bytes += int(snapshot.get("size", 0) or 0)
        if previous.get(file_name) != current.get(file_name):
            changed_files.append(file_name)
    return changed_files, source_db_count, source_bytes


def parse_decrypt_metrics(decrypt_result: dict) -> list[dict]:
    metrics: list[dict] = []
    for line in str(decrypt_result.get("stdout") or "").splitlines():
        if not line.startswith("WXWORK_DECRYPT_METRIC "):
            continue
        raw = line.removeprefix("WXWORK_DECRYPT_METRIC ").strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            metrics.append(parsed)
    return metrics


def decrypt_metrics_summary(decrypt_result: dict) -> dict:
    metrics = parse_decrypt_metrics(decrypt_result)
    return {
        "decrypt_db_count": len(metrics),
        "decrypt_bytes": sum(int(item.get("output_bytes") or 0) for item in metrics),
        "copied_bytes": sum(int(item.get("copied_bytes") or 0) for item in metrics),
        "decrypt_metrics": metrics,
    }


def log_latency_stage(stage: str, **payload) -> None:
    safe_payload = {
        "stage": stage,
        "at": utcnow_iso(),
        **{key: value for key, value in payload.items() if value is not None},
    }
    log_info("latency_stage " + compact_json(safe_payload))


def is_source_refresh_stale(
    last_refresh_completed_at: str | None,
    *,
    max_staleness_ms: int = MAX_SOURCE_STALENESS_MS,
    now_at: str | None = None,
) -> bool:
    last_refresh = iso_to_datetime(last_refresh_completed_at)
    current = iso_to_datetime(now_at or utcnow_iso())
    if last_refresh is None or current is None:
        return True
    elapsed_ms = (current - last_refresh).total_seconds() * 1000
    return elapsed_ms >= max(0, int(max_staleness_ms))


@dataclass
class AdaptivePollController:
    current_interval_ms: int = ACTIVE_POLL_INTERVAL_MS

    def record_result(self, *, had_activity: bool, had_error: bool) -> None:
        if had_activity or had_error:
            self.current_interval_ms = ACTIVE_POLL_INTERVAL_MS
            return
        if self.current_interval_ms <= ACTIVE_POLL_INTERVAL_MS:
            self.current_interval_ms = FIRST_IDLE_POLL_INTERVAL_MS
            return
        self.current_interval_ms = MAX_IDLE_POLL_INTERVAL_MS


def build_monitor_cursor(message: dict) -> dict:
    return wxwork_query.build_monitor_cursor(message)


def load_monitor_cursor(store: "MonitorStateStore") -> dict | None:
    raw = store.get_state("monitor_cursor")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def save_monitor_cursor(store: "MonitorStateStore", cursor: dict | None) -> None:
    if cursor is None:
        return
    store.set_state("monitor_cursor", json.dumps(cursor, ensure_ascii=False, separators=(",", ":")))


def ensure_timing_payload(payload: dict) -> dict:
    timings = payload.get("timings")
    if not isinstance(timings, dict):
        timings = {}
        payload["timings"] = timings
    for field in TIMING_FIELDS:
        timings.setdefault(field, None)
    return timings


def set_timing(payload: dict, field: str, value: str | None = None) -> str:
    timings = ensure_timing_payload(payload)
    resolved = value or utcnow_iso()
    timings[field] = resolved
    return resolved


class MonitorStateStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_snapshots (
                    path TEXT PRIMARY KEY,
                    file_exists INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_messages (
                    message_key TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    seen_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY,
                    message_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    delivered_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def set_state(self, key: str, value: object) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO monitor_state(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_state(self, key: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT value FROM monitor_state WHERE key = ?", (key,)).fetchone()
            return None if row is None else str(row["value"])
        finally:
            conn.close()

    def load_file_snapshots(self) -> dict[str, dict[str, int]]:
        conn = self._connect()
        try:
            snapshots: dict[str, dict[str, int]] = {}
            for row in conn.execute("SELECT path, file_exists, size, mtime_ns FROM file_snapshots"):
                snapshots[str(row["path"])] = {
                    "exists": int(row["file_exists"]),
                    "size": int(row["size"]),
                    "mtime_ns": int(row["mtime_ns"]),
                }
            return snapshots
        finally:
            conn.close()

    def save_file_snapshots(self, snapshots: dict[str, dict[str, int]]) -> None:
        conn = self._connect()
        try:
            now = utcnow_iso()
            conn.execute("DELETE FROM file_snapshots")
            for path, snapshot in snapshots.items():
                conn.execute(
                    """
                    INSERT INTO file_snapshots(path, file_exists, size, mtime_ns, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        path,
                        int(snapshot["exists"]),
                        int(snapshot["size"]),
                        int(snapshot["mtime_ns"]),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def has_seen_message(self, message_key: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM seen_messages WHERE message_key = ?",
                (message_key,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def record_seen_and_enqueue(self, event_id: str, message_key: str, payload: dict) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM seen_messages WHERE message_key = ?",
                (message_key,),
            ).fetchone()
            if row is not None:
                return False
            now = utcnow_iso()
            set_timing(payload, "outbox_created_at", now)
            conn.execute(
                """
                INSERT INTO seen_messages(message_key, event_id, seen_at)
                VALUES (?, ?, ?)
                """,
                (message_key, event_id, now),
            )
            conn.execute(
                """
                INSERT INTO outbox(
                    event_id, message_key, payload_json, status, attempt_count,
                    next_attempt_at, last_error, delivered_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, 0, NULL, NULL, ?, ?)
                """,
                (
                    event_id,
                    message_key,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    OUTBOX_STATUS_PENDING,
                    now,
                    now,
                ),
            )
            self._prune_seen_messages(conn, MAX_SEEN_MESSAGES)
            conn.commit()
            return True
        finally:
            conn.close()

    def _prune_seen_messages(self, conn: sqlite3.Connection, keep_limit: int) -> None:
        total_row = conn.execute("SELECT COUNT(*) FROM seen_messages").fetchone()
        total = int(total_row[0] or 0)
        if total <= keep_limit:
            return
        delete_count = total - keep_limit
        conn.execute(
            """
            DELETE FROM seen_messages
            WHERE message_key IN (
                SELECT message_key FROM seen_messages
                ORDER BY seen_at ASC
                LIMIT ?
            )
            """,
            (delete_count,),
        )

    def mark_seen_only(self, event_id: str, message_key: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_messages(message_key, event_id, seen_at)
                VALUES (?, ?, ?)
                """,
                (message_key, event_id, utcnow_iso()),
            )
            self._prune_seen_messages(conn, MAX_SEEN_MESSAGES)
            conn.commit()
        finally:
            conn.close()

    def list_due_outbox_rows(self, now_ts: float) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM outbox
                WHERE status != ? AND next_attempt_at <= ?
                ORDER BY created_at ASC
                """,
                (OUTBOX_STATUS_DELIVERED, now_ts),
            ).fetchall()
            return rows
        finally:
            conn.close()

    def mark_outbox_delivered(self, event_id: str, payload: dict | None = None) -> None:
        conn = self._connect()
        try:
            now = utcnow_iso()
            conn.execute(
                """
                UPDATE outbox
                SET status = ?, payload_json = COALESCE(?, payload_json), delivered_at = ?, updated_at = ?, last_error = NULL
                WHERE event_id = ?
                """,
                (
                    OUTBOX_STATUS_DELIVERED,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload is not None else None,
                    now,
                    now,
                    event_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_outbox_retry(self, event_id: str, attempt_count: int, next_attempt_at: float, last_error: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE outbox
                SET status = ?, attempt_count = ?, next_attempt_at = ?, last_error = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (
                    OUTBOX_STATUS_PENDING,
                    attempt_count,
                    next_attempt_at,
                    last_error,
                    utcnow_iso(),
                    event_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WXWork near-real-time database monitor")
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--debounce-ms", type=int, default=DEFAULT_DEBOUNCE_MS)
    parser.add_argument("--scan-limit", type=int, default=DEFAULT_SCAN_LIMIT)
    parser.add_argument("--stability-checks", type=int, default=DEFAULT_STABILITY_CHECKS)
    parser.add_argument("--stability-interval-ms", type=int, default=DEFAULT_STABILITY_INTERVAL_MS)
    parser.add_argument("--max-stability-wait-ms", type=int, default=DEFAULT_MAX_STABILITY_WAIT_MS)
    return parser


def snapshot_files(db_dir: str) -> dict[str, dict[str, int]]:
    snapshots: dict[str, dict[str, int]] = {}
    for file_name in MONITORED_FILES:
        path = os.path.join(db_dir, file_name)
        try:
            stat = os.stat(path)
            snapshots[file_name] = {
                "exists": 1,
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            }
        except FileNotFoundError:
            snapshots[file_name] = {
                "exists": 0,
                "size": 0,
                "mtime_ns": 0,
            }
    return snapshots


def snapshots_changed(previous: dict[str, dict[str, int]], current: dict[str, dict[str, int]]) -> bool:
    for file_name in MONITORED_FILES:
        if previous.get(file_name) != current.get(file_name):
            return True
    return False


def determine_refresh_targets(
    previous: dict[str, dict[str, int]],
    current: dict[str, dict[str, int]],
) -> list[str]:
    targets: list[str] = []
    if any(previous.get(name) != current.get(name) for name in ("message.db", "message.db-wal", "message.db-shm")):
        targets.append(REFRESH_TARGET_MESSAGE)
    if any(previous.get(name) != current.get(name) for name in ("session.db", "session.db-wal", "session.db-shm")):
        targets.append(REFRESH_TARGET_SESSION)
    if any(previous.get(name) != current.get(name) for name in ("user.db", "user.db-wal")):
        targets.append(REFRESH_TARGET_USER)
    return targets


def wait_for_stable_snapshot(
    db_dir: str,
    initial_snapshot: dict[str, dict[str, int]],
    *,
    stability_checks: int,
    stability_interval_ms: int,
    max_stability_wait_ms: int,
) -> dict[str, object]:
    required_matches = max(1, int(stability_checks or 1))
    interval_seconds = max(0, int(stability_interval_ms or 0)) / 1000
    deadline = monotonic_seconds() + max(0, int(max_stability_wait_ms or 0)) / 1000
    candidate_snapshot = initial_snapshot
    consecutive_matches = 0

    while True:
        time.sleep(interval_seconds)
        current_snapshot = snapshot_files(db_dir)
        if current_snapshot == candidate_snapshot:
            consecutive_matches += 1
            if consecutive_matches >= required_matches:
                return {"snapshot": current_snapshot, "stable": True}
        else:
            candidate_snapshot = current_snapshot
            consecutive_matches = 1
        if monotonic_seconds() >= deadline:
            return {"snapshot": current_snapshot, "stable": False}


def canonical_message_hash_payload(message: dict) -> dict:
    return {
        "source_table": message["source_table"],
        "conversation_id": message["conversation_id"],
        "message_id": message["message_id"],
        "server_id": message["server_id"],
        "send_time": message["send_time"],
        "sender_id": message["sender_id"],
        "source_rowid": message["source_rowid"],
    }


def build_message_key(message: dict) -> tuple[str, str]:
    canonical = json.dumps(
        canonical_message_hash_payload(message),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"wxwork:{digest}", f"wxwork-local:{digest}"


def build_event_payload(message: dict, message_key: str, event_id: str) -> dict:
    return {
        "connector_id": "wxwork-local",
        "source": "wxwork",
        "event_id": event_id,
        "message_key": message_key,
        "conversation": {
            "external_conversation_id": message["conversation_id"],
            "conversation_name": message["conversation_name"],
            "conversation_type": message["conversation_type"],
        },
        "message": {
            "external_message_id": str(message["message_id"]) if int(message["message_id"] or 0) > 0 else None,
            "sender_id": str(message["sender_id"]),
            "sender_name": str(message["sender_name"]),
            "content": message["content"],
            "message_type": "text",
            "sent_at": sent_time_to_iso(int(message["send_time"] or 0)),
            "observed_at": utcnow_iso(),
            "content_summary": message["content_summary"],
            "source_table": message["source_table"],
            "server_id": int(message["server_id"] or 0),
            "sequence": int(message["sequence"] or 0),
            "source_rowid": int(message["source_rowid"] or 0),
        },
    }


def refresh_decrypted_cache(runtime_dir: str, database_list: list[str] | None = None) -> dict:
    return connector_runtime.decrypt("wxwork", runtime_dir, database_list=database_list)


def get_runtime_state_paths(runtime_dir: str) -> tuple[str, str]:
    runtime = connector_runtime.load_runtime_config("wxwork", runtime_dir)
    if runtime is None:
        raise RuntimeError("WXWork runtime configuration is missing. Run connector setup again.")
    db_dir = str(runtime.get("db_dir") or "")
    decrypted_dir = str(runtime.get("config", {}).get("wxwork_decrypted_dir") or runtime.get("decrypted_dir") or "")
    if not db_dir or not os.path.isdir(db_dir):
        raise RuntimeError("Configured WXWork database directory does not exist")
    if not decrypted_dir:
        raise RuntimeError("Configured WXWork decrypted directory is missing")
    return db_dir, decrypted_dir


def push_event(url: str, token: str, payload: dict) -> tuple[bool, str, dict | None]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Wecome-Connector-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}", None
    except urllib.error.URLError as exc:
        return False, f"Network error: {exc.reason}", None
    try:
        response_payload = json.loads(body)
    except json.JSONDecodeError:
        return False, "Invalid JSON response", None
    data_payload = response_payload.get("data") or {}
    if data_payload.get("accepted") is True:
        timings = data_payload.get("timings") if isinstance(data_payload.get("timings"), dict) else None
        return True, "accepted", timings
    return False, "Rejected by LangBot", None


def next_retry_delay_seconds(attempt_count: int) -> int:
    return min(60, 2 ** min(max(attempt_count, 1), 6))


def log_info(message: str) -> None:
    print(f"[wxwork-monitor] {message}", flush=True)


def log_error(message: str) -> None:
    print(f"[wxwork-monitor][error] {message}", file=sys.stderr, flush=True)


def perform_warmup(store: MonitorStateStore, runtime_dir: str, scan_limit: int) -> None:
    log_info("Running initial warmup")
    decrypt_result = refresh_decrypted_cache(runtime_dir)
    if not decrypt_result.get("ok"):
        raise RuntimeError(decrypt_result.get("error_message") or "Decrypt failed during warmup")
    messages = run_with_sqlite_retry(lambda: wxwork_query.get_messages_for_monitor(limit=scan_limit))
    for message in messages:
        message_key, event_id = build_message_key(message)
        store.mark_seen_only(event_id, message_key)
    if messages:
        save_monitor_cursor(store, build_monitor_cursor(messages[0]))
    store.set_state("warmup_completed", "true")
    store.set_state("last_error", "")
    log_info(f"Warmup completed with {len(messages)} existing messages recorded")


def log_stage(message_key: str, stage_name: str, timings: dict, *, scanned_count: int, new_count: int) -> None:
    stage_order = list(TIMING_FIELDS)
    current_at = timings.get(stage_name)
    if current_at is None:
        return
    current_index = stage_order.index(stage_name)
    previous_at = None
    for index in range(current_index - 1, -1, -1):
        previous_at = timings.get(stage_order[index])
        if previous_at:
            break
    stage_elapsed = duration_ms(previous_at, current_at) if previous_at else None
    total_elapsed = duration_ms(timings.get("file_change_detected_at"), current_at)
    log_info(
        f"{hash_prefix(message_key)} stage={stage_name} stage_ms={stage_elapsed if stage_elapsed is not None else '-'} "
        f"total_ms={total_elapsed if total_elapsed is not None else '-'} scanned={scanned_count} new={new_count}"
    )


def scan_and_enqueue(
    store: MonitorStateStore,
    runtime_dir: str,
    scan_limit: int,
    *,
    refresh_targets: list[str] | None = None,
    base_timings: dict[str, str | None] | None = None,
) -> dict[str, object]:
    poll_id = str((base_timings or {}).get("poll_id") or uuid.uuid4())
    cursor = load_monitor_cursor(store)
    log_latency_stage(
        "decrypt_started",
        poll_id=poll_id,
        refresh_targets=refresh_targets,
        cursor_before=cursor,
        **{key: value for key, value in (base_timings or {}).items() if key != "poll_id"},
    )
    decrypt_started_at = utcnow_iso()
    decrypt_result = run_with_sqlite_retry(
        lambda: refresh_decrypted_cache(runtime_dir, database_list=refresh_targets)
    )
    if isinstance(decrypt_result, dict):
        decrypt_ok = bool(decrypt_result.get("ok"))
        decrypt_error_message = decrypt_result.get("error_message")
    else:
        decrypt_ok = decrypt_result is not False
        decrypt_error_message = None
    if not decrypt_ok:
        raise RuntimeError(str(decrypt_error_message or "Decrypt refresh failed"))
    decrypt_completed_at = utcnow_iso()
    decrypt_summary = decrypt_metrics_summary(decrypt_result if isinstance(decrypt_result, dict) else {})
    log_latency_stage(
        "decrypt_completed",
        poll_id=poll_id,
        refresh_targets=refresh_targets,
        elapsed_ms=duration_ms(decrypt_started_at, decrypt_completed_at),
        **decrypt_summary,
    )
    log_latency_stage(
        "query_started",
        poll_id=poll_id,
        cursor_before=cursor,
        scan_limit=scan_limit,
        lookback_seconds=DEFAULT_MONITOR_LOOKBACK_SECONDS,
    )
    scanned_messages = run_with_sqlite_retry(
        lambda: wxwork_query.get_messages_for_monitor(
            limit=scan_limit,
            after_cursor=cursor,
            lookback_seconds=DEFAULT_MONITOR_LOOKBACK_SECONDS,
        )
    )
    scan_completed_at = utcnow_iso()
    new_messages = 0
    latest_cursor: dict | None = None
    for index, message in enumerate(scanned_messages, start=1):
        message_key, event_id = build_message_key(message)
        payload = build_event_payload(message, message_key, event_id)
        timings = ensure_timing_payload(payload)
        for key, value in (base_timings or {}).items():
            if key in timings and value:
                timings[key] = value
        payload["poll_id"] = poll_id
        timings["decrypt_started_at"] = decrypt_started_at
        timings["decrypt_completed_at"] = decrypt_completed_at
        timings["scan_completed_at"] = scan_completed_at
        if store.record_seen_and_enqueue(event_id, message_key, payload):
            new_messages += 1
            log_latency_stage(
                "new_row_first_visible",
                poll_id=poll_id,
                event_id=event_id,
                message_key_hash=hash_prefix(message_key),
                rows_scanned=index,
                new_rows=new_messages,
                cursor_before=cursor,
            )
            log_stage(message_key, "outbox_created_at", timings, scanned_count=index, new_count=new_messages)
        latest_cursor = latest_cursor or build_monitor_cursor(message)
    log_latency_stage(
        "query_completed",
        poll_id=poll_id,
        rows_scanned=len(scanned_messages),
        new_rows=new_messages,
        cursor_before=cursor,
        cursor_after=latest_cursor,
        elapsed_ms=duration_ms(decrypt_completed_at, scan_completed_at),
    )
    if new_messages:
        store.set_state("last_event_at", utcnow_iso())
    if latest_cursor is not None:
        save_monitor_cursor(store, latest_cursor)
    return {
        "new_messages": new_messages,
        "scanned_messages": len(scanned_messages),
        "latest_cursor": latest_cursor,
        "decrypt_started_at": decrypt_started_at,
        "decrypt_completed_at": decrypt_completed_at,
        "scan_completed_at": scan_completed_at,
        "poll_id": poll_id,
    }


def run_refresh_cycle(
    store: MonitorStateStore,
    runtime_dir: str,
    scan_limit: int,
    *,
    refresh_targets: list[str] | tuple[str, ...] | None = None,
    base_timings: dict[str, str | None] | None = None,
    confirmation_delay_ms: int = 0,
) -> dict[str, object]:
    result = scan_and_enqueue(
        store,
        runtime_dir,
        scan_limit,
        refresh_targets=list(refresh_targets) if refresh_targets is not None else None,
        base_timings=base_timings,
    )
    if int(result["new_messages"]) > 0 or confirmation_delay_ms <= 0:
        return result

    time.sleep(max(0, int(confirmation_delay_ms)) / 1000)
    confirm_result = scan_and_enqueue(
        store,
        runtime_dir,
        scan_limit,
        refresh_targets=list(refresh_targets) if refresh_targets is not None else None,
        base_timings=base_timings,
    )
    return {
        "new_messages": int(result["new_messages"]) + int(confirm_result["new_messages"]),
        "scanned_messages": int(result["scanned_messages"]) + int(confirm_result["scanned_messages"]),
        "latest_cursor": confirm_result.get("latest_cursor") or result.get("latest_cursor"),
        "decrypt_started_at": confirm_result.get("decrypt_started_at") or result.get("decrypt_started_at"),
        "decrypt_completed_at": confirm_result.get("decrypt_completed_at") or result.get("decrypt_completed_at"),
        "scan_completed_at": confirm_result.get("scan_completed_at") or result.get("scan_completed_at"),
    }


def deliver_outbox(store: MonitorStateStore, push_url: str, token_file: str) -> None:
    if not os.path.exists(token_file):
        raise RuntimeError("Connector token file is missing")
    token = Path(token_file).read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Connector token is empty")
    for row in store.list_due_outbox_rows(time.time()):
        payload = json.loads(row["payload_json"])
        push_result = push_event(push_url, token, payload)
        if len(push_result) == 3:
            success, message, returned_timings = push_result
        else:
            success, message = push_result
            returned_timings = None
        if success:
            timings = ensure_timing_payload(payload)
            message_key = str(row["message_key"])
            if isinstance(returned_timings, dict):
                for field in ("langbot_ingested_at", "sse_published_at"):
                    value = returned_timings.get(field)
                    if value:
                        timings[field] = str(value)
                        log_stage(
                            message_key,
                            field,
                            timings,
                            scanned_count=0,
                            new_count=0,
                        )
            timings["delivery_succeeded_at"] = utcnow_iso()
            store.mark_outbox_delivered(str(row["event_id"]), payload=payload)
            store.set_state("last_error", "")
            log_stage(
                message_key,
                "delivery_succeeded_at",
                timings,
                scanned_count=0,
                new_count=0,
            )
            continue
        attempt_count = int(row["attempt_count"] or 0) + 1
        delay = next_retry_delay_seconds(attempt_count)
        store.mark_outbox_retry(
            str(row["event_id"]),
            attempt_count=attempt_count,
            next_attempt_at=time.time() + delay,
            last_error=message,
        )
        store.set_state("last_error", message)
        log_error(f"Outbox delivery failed, retry in {delay}s: {message}")


def execute_monitor_iteration(
    store: MonitorStateStore,
    *,
    db_dir: str,
    runtime_dir: str,
    scan_limit: int,
    push_url: str,
    token_file: str,
    stability_checks: int,
    stability_interval_ms: int,
    max_stability_wait_ms: int,
    previous_snapshot: dict[str, dict[str, int]],
    last_processed_snapshot: dict[str, dict[str, int]] | None,
    immediate_reruns_remaining: int,
    poll_interval_ms: int,
) -> dict[str, object]:
    poll_id = str(uuid.uuid4())
    started_monotonic = monotonic_seconds()
    rows_scanned = 0
    new_rows = 0
    had_error = False
    next_previous_snapshot = previous_snapshot
    next_last_processed_snapshot = last_processed_snapshot
    next_immediate_reruns_remaining = immediate_reruns_remaining

    store.set_state("last_scan_at", utcnow_iso())
    store.set_state("poll_interval_ms", poll_interval_ms)
    store.set_state("poll_seconds", max(1, int((poll_interval_ms + 999) / 1000)))
    log_info(f"poll_started poll_id={poll_id} poll_interval_ms={poll_interval_ms}")

    try:
        current_snapshot = run_with_sqlite_retry(lambda: snapshot_files(db_dir))
        changed = snapshots_changed(previous_snapshot, current_snapshot)
        force_stale_refresh = not changed and is_source_refresh_stale(store.get_state("last_refresh_completed_at"))
        if changed:
            file_change_detected_at = utcnow_iso()
            changed_files, source_db_count, source_bytes = summarize_snapshot_changes(previous_snapshot, current_snapshot)
            log_latency_stage(
                "source_signature_changed",
                poll_id=poll_id,
                poll_interval_ms=poll_interval_ms,
                scan_reason="signature_changed",
                changed_files=changed_files,
                source_db_count=source_db_count,
                source_bytes=source_bytes,
            )
            log_latency_stage(
                "source_snapshot_copy_started",
                poll_id=poll_id,
                poll_interval_ms=poll_interval_ms,
                scan_reason="signature_changed",
                changed_files=changed_files,
            )
            stable_result = wait_for_stable_snapshot(
                db_dir,
                current_snapshot,
                stability_checks=stability_checks,
                stability_interval_ms=stability_interval_ms,
                max_stability_wait_ms=max_stability_wait_ms,
            )
            stable_snapshot = stable_result["snapshot"]
            refresh_targets = determine_refresh_targets(previous_snapshot, stable_snapshot)
            stable_changed_files, stable_source_db_count, stable_source_bytes = summarize_snapshot_changes(
                previous_snapshot,
                stable_snapshot,
            )
            log_latency_stage(
                "source_snapshot_copy_completed",
                poll_id=poll_id,
                poll_interval_ms=poll_interval_ms,
                scan_reason="signature_changed",
                changed_files=stable_changed_files,
                source_db_count=stable_source_db_count,
                source_bytes=stable_source_bytes,
                stable=stable_result.get("stable"),
            )
            log_latency_stage(
                "wal_shm_sync_started",
                poll_id=poll_id,
                changed_files=[name for name in stable_changed_files if name.endswith(("-wal", "-shm"))],
            )
            log_latency_stage(
                "wal_shm_sync_completed",
                poll_id=poll_id,
                changed_files=[name for name in stable_changed_files if name.endswith(("-wal", "-shm"))],
            )
            next_previous_snapshot = stable_snapshot
            store.save_file_snapshots(stable_snapshot)
            store.set_state("last_change_at", file_change_detected_at)

            if stable_snapshot == last_processed_snapshot:
                next_immediate_reruns_remaining = 1
            elif refresh_targets:
                result = run_refresh_cycle(
                    store,
                    runtime_dir,
                    scan_limit,
                    refresh_targets=refresh_targets,
                    base_timings={
                        "poll_id": poll_id,
                        "file_change_detected_at": file_change_detected_at,
                        "stability_completed_at": utcnow_iso(),
                    },
                    confirmation_delay_ms=POST_CHANGE_CONFIRMATION_DELAY_MS,
                )
                rows_scanned += int(result["scanned_messages"])
                new_rows += int(result["new_messages"])
                next_last_processed_snapshot = stable_snapshot
                store.set_state("last_refresh_completed_at", utcnow_iso())
                store.set_state("running_status", "running")
                store.set_state("last_error", "")
                if int(result["new_messages"]) > 0:
                    log_info(f"Queued {result['new_messages']} new messages scanned={result['scanned_messages']}")
                    deliver_outbox(store, push_url, token_file)
                post_cycle_snapshot = run_with_sqlite_retry(lambda: snapshot_files(db_dir))
                if next_immediate_reruns_remaining > 0 and snapshots_changed(stable_snapshot, post_cycle_snapshot):
                    next_immediate_reruns_remaining -= 1
                    next_previous_snapshot = post_cycle_snapshot
                    store.save_file_snapshots(post_cycle_snapshot)
                    elapsed_ms = int((monotonic_seconds() - started_monotonic) * 1000)
                    log_info(
                        "poll_completed "
                        f"poll_interval_ms={poll_interval_ms} rows_scanned={rows_scanned} "
                        f"new_rows={new_rows} elapsed_ms={elapsed_ms}"
                    )
                    return {
                        "previous_snapshot": next_previous_snapshot,
                        "last_processed_snapshot": next_last_processed_snapshot,
                        "immediate_reruns_remaining": next_immediate_reruns_remaining,
                        "rows_scanned": rows_scanned,
                        "new_rows": new_rows,
                        "had_error": False,
                        "continue_immediately": True,
                    }
                next_immediate_reruns_remaining = 1
        elif force_stale_refresh:
            staleness_refresh_started_at = utcnow_iso()
            changed_files, source_db_count, source_bytes = summarize_snapshot_changes(previous_snapshot, current_snapshot)
            log_latency_stage(
                "source_signature_changed",
                poll_id=poll_id,
                poll_interval_ms=poll_interval_ms,
                scan_reason="staleness",
                changed_files=changed_files,
                source_db_count=source_db_count,
                source_bytes=source_bytes,
            )
            result = run_refresh_cycle(
                store,
                runtime_dir,
                scan_limit,
                refresh_targets=STALE_REFRESH_TARGETS,
                base_timings={
                    "poll_id": poll_id,
                    "file_change_detected_at": staleness_refresh_started_at,
                },
            )
            rows_scanned += int(result["scanned_messages"])
            new_rows += int(result["new_messages"])
            next_previous_snapshot = current_snapshot
            next_last_processed_snapshot = current_snapshot
            store.save_file_snapshots(current_snapshot)
            store.set_state("last_refresh_completed_at", utcnow_iso())
            store.set_state("running_status", "running")
            store.set_state("last_error", "")
            if int(result["new_messages"]) > 0:
                log_info(
                    "Queued "
                    f"{result['new_messages']} new messages scanned={result['scanned_messages']} refresh_reason=staleness"
                )
                deliver_outbox(store, push_url, token_file)
        deliver_outbox(store, push_url, token_file)
        store.set_state("running_status", "running")
        store.set_state("last_error", "")
    except Exception as exc:
        had_error = True
        next_immediate_reruns_remaining = 1
        store.set_state("running_status", "error")
        store.set_state("last_error", str(exc))
        log_error(str(exc))

    elapsed_ms = int((monotonic_seconds() - started_monotonic) * 1000)
    log_info(
        "poll_completed "
        f"poll_id={poll_id} poll_interval_ms={poll_interval_ms} rows_scanned={rows_scanned} "
        f"new_rows={new_rows} elapsed_ms={elapsed_ms}"
    )
    return {
        "previous_snapshot": next_previous_snapshot,
        "last_processed_snapshot": next_last_processed_snapshot,
        "immediate_reruns_remaining": next_immediate_reruns_remaining,
        "rows_scanned": rows_scanned,
        "new_rows": new_rows,
        "had_error": had_error,
        "continue_immediately": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime_dir = connector_runtime.resolve_runtime_dir(args.runtime_dir)
    push_url = os.environ.get("WECOME_LANGBOT_INTERNAL_EVENT_URL", "").strip()
    token_file = os.environ.get("WECOME_INTERNAL_EVENT_TOKEN_FILE", "").strip()
    if not push_url:
        raise SystemExit("WECOME_LANGBOT_INTERNAL_EVENT_URL is required")
    if not token_file:
        raise SystemExit("WECOME_INTERNAL_EVENT_TOKEN_FILE is required")

    db_dir, _decrypted_dir = get_runtime_state_paths(runtime_dir)
    monitor_db = os.environ.get("WECOME_MONITOR_STATE_DB", "").strip()
    if not monitor_db:
        monitor_db = str(Path(runtime_dir) / "monitor" / "monitor_state.db")
    store = MonitorStateStore(monitor_db)
    store.set_state("poll_seconds", args.poll_seconds)
    store.set_state("debounce_ms", args.debounce_ms)
    store.set_state("scan_limit", args.scan_limit)
    store.set_state("stability_checks", args.stability_checks)
    store.set_state("stability_interval_ms", args.stability_interval_ms)
    store.set_state("max_stability_wait_ms", args.max_stability_wait_ms)
    store.set_state("running_status", "starting")

    if store.get_state("warmup_completed") != "true":
        store.set_state("running_status", "warming_up")
        perform_warmup(store, runtime_dir, args.scan_limit)

    previous_snapshot = store.load_file_snapshots()
    if not previous_snapshot:
        previous_snapshot = snapshot_files(db_dir)
        store.save_file_snapshots(previous_snapshot)

    store.set_state("running_status", "running")
    log_info("WXWork monitor started")

    poll_controller = AdaptivePollController()
    immediate_reruns_remaining = 1
    last_processed_snapshot: dict[str, dict[str, int]] | None = None
    store.set_state("last_refresh_completed_at", store.get_state("last_refresh_completed_at") or utcnow_iso())

    while True:
        iteration_result = execute_monitor_iteration(
            store,
            db_dir=db_dir,
            runtime_dir=runtime_dir,
            scan_limit=args.scan_limit,
            push_url=push_url,
            token_file=token_file,
            stability_checks=args.stability_checks,
            stability_interval_ms=args.stability_interval_ms,
            max_stability_wait_ms=args.max_stability_wait_ms,
            previous_snapshot=previous_snapshot,
            last_processed_snapshot=last_processed_snapshot,
            immediate_reruns_remaining=immediate_reruns_remaining,
            poll_interval_ms=poll_controller.current_interval_ms,
        )
        previous_snapshot = iteration_result["previous_snapshot"]
        last_processed_snapshot = iteration_result["last_processed_snapshot"]
        immediate_reruns_remaining = int(iteration_result["immediate_reruns_remaining"])
        if iteration_result["continue_immediately"]:
            poll_controller.record_result(
                had_activity=bool(iteration_result["new_rows"]),
                had_error=bool(iteration_result["had_error"]),
            )
            continue
        poll_controller.record_result(
            had_activity=bool(iteration_result["new_rows"]),
            had_error=bool(iteration_result["had_error"]),
        )
        time.sleep(poll_controller.current_interval_ms / 1000)


if __name__ == "__main__":
    raise SystemExit(main())
