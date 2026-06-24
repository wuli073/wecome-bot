from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from config import _app_base_dir, _config_file_path
from export_wxwork_messages import (
    MSG_TYPES,
    _MESSAGE_TABLES,
    _build_message as _shared_build_message,
    _conversation_kind as _shared_conversation_kind,
    _format_time as _shared_format_time,
    _name_from_conversation_id as _shared_name_from_conversation_id,
    decode_content,
)

_MAX_HISTORY_LIMIT = 100
_MAX_SEARCH_LIMIT = 100
_MAX_RECENT_LIMIT = 100
_MAX_CONTACT_LIMIT = 200
_CONVERSATION_ID_RE = re.compile(r"^[A-Za-z0-9:_-]{1,128}$")
_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def _load_config() -> dict[str, Any]:
    base = _app_base_dir()
    config_file = _config_file_path()
    cfg: dict[str, Any] = {}
    if os.path.exists(config_file):
        with open(config_file, encoding="utf-8") as handle:
            cfg = json.load(handle)

    decrypted_dir = cfg.get("wxwork_decrypted_dir", "wxwork_decrypted")
    if not os.path.isabs(decrypted_dir):
        decrypted_dir = os.path.join(base, decrypted_dir)

    db_dir = cfg.get("wxwork_db_dir", "")
    return {
        "base": base,
        "decrypted_dir": os.path.abspath(decrypted_dir),
        "self_id": _infer_self_id(db_dir),
    }


def _infer_self_id(db_dir: str) -> int | None:
    if not db_dir:
        return None
    parts = os.path.normpath(db_dir).split(os.sep)
    for part in reversed(parts):
        if part.isdigit() and len(part) >= 10:
            return int(part)
    return None


def _require_decrypted_dir() -> str:
    decrypted_dir = _load_config()["decrypted_dir"]
    if not os.path.isdir(decrypted_dir):
        raise FileNotFoundError("wxwork_decrypted directory does not exist")
    return decrypted_dir


def _readonly_uri(path: str) -> str:
    return Path(path).resolve().as_uri() + "?mode=ro"


def _open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _message_type_name(content_type: int | None) -> str:
    return MSG_TYPES.get(int(content_type or 0), f"unknown({content_type})")


def _load_user_map(decrypted_dir: str) -> dict[int, str]:
    user_db = os.path.join(decrypted_dir, "user.db")
    if not os.path.exists(user_db):
        return {}

    users: dict[int, str] = {}
    conn = _open_db(user_db)
    try:
        if _table_exists(conn, "user_table"):
            for row in conn.execute(
                "SELECT id, name, real_name, account, external_corp_name "
                "FROM user_table"
            ):
                name = row["real_name"] or row["name"] or row["account"] or ""
                if row["external_corp_name"] and row["external_corp_name"] not in name:
                    name = (
                        f"{name} ({row['external_corp_name']})"
                        if name
                        else row["external_corp_name"]
                    )
                if name:
                    users[int(row["id"])] = name

        if _table_exists(conn, "external_user_relation_v3"):
            for row in conn.execute(
                "SELECT user_id, remarks, real_remarks, corp_remark "
                "FROM external_user_relation_v3"
            ):
                name = row["real_remarks"] or row["remarks"] or row["corp_remark"] or ""
                if name:
                    users[int(row["user_id"])] = name
    finally:
        conn.close()

    return users


def _load_group_member_names(decrypted_dir: str) -> dict[str, dict[int, str]]:
    session_db = os.path.join(decrypted_dir, "session.db")
    members: dict[str, dict[int, str]] = defaultdict(dict)
    if not os.path.exists(session_db):
        return members

    conn = _open_db(session_db)
    try:
        if _table_exists(conn, "conversation_user_table"):
            for row in conn.execute(
                "SELECT conversation_id, user_id, nick_name FROM conversation_user_table"
            ):
                if row["nick_name"]:
                    members[row["conversation_id"]][int(row["user_id"])] = row["nick_name"]

        if _table_exists(conn, "conversation_member_nickname_table"):
            room_map: dict[int, str] = {}
            if _table_exists(conn, "conversation_table"):
                for row in conn.execute("SELECT con_numeric_id, id FROM conversation_table"):
                    if row["con_numeric_id"] is not None:
                        room_map[int(row["con_numeric_id"])] = row["id"]
            for row in conn.execute(
                "SELECT room_id, userid, nickname FROM conversation_member_nickname_table"
            ):
                cid = room_map.get(int(row["room_id"]))
                if cid and row["nickname"]:
                    members[cid][int(row["userid"])] = row["nickname"]
    finally:
        conn.close()

    return members


def _load_message_counts(decrypted_dir: str) -> tuple[dict[str, int], dict[str, int]]:
    message_db = os.path.join(decrypted_dir, "message.db")
    counts: dict[str, int] = defaultdict(int)
    last_times: dict[str, int] = defaultdict(int)
    if not os.path.exists(message_db):
        return counts, last_times

    conn = _open_db(message_db)
    try:
        for table in _MESSAGE_TABLES:
            _validate_message_table(table)
            if not _table_exists(conn, table):
                continue
            for row in conn.execute(
                f'SELECT conversation_id, COUNT(*) AS c, MAX(send_time) AS t '
                f'FROM "{table}" GROUP BY conversation_id'
            ):
                conversation_id = row["conversation_id"]
                if not conversation_id:
                    continue
                counts[conversation_id] += int(row["c"] or 0)
                last_times[conversation_id] = max(
                    last_times[conversation_id],
                    int(row["t"] or 0),
                )
    finally:
        conn.close()

    return counts, last_times


def discover_conversations(decrypted_dir: str | None = None) -> list[dict[str, Any]]:
    cfg = _load_config()
    decrypted_dir = decrypted_dir or cfg["decrypted_dir"]
    if not os.path.isdir(decrypted_dir):
        raise FileNotFoundError("wxwork_decrypted directory does not exist")

    user_map = _load_user_map(decrypted_dir)
    counts, last_times = _load_message_counts(decrypted_dir)
    session_db = os.path.join(decrypted_dir, "session.db")
    conversations: dict[str, dict[str, Any]] = {}

    if os.path.exists(session_db):
        conn = _open_db(session_db)
        try:
            if _table_exists(conn, "conversation_table"):
                for row in conn.execute(
                    "SELECT id, name, roomname_remark, last_message_time, last_message_id "
                    "FROM conversation_table"
                ):
                    conversation_id = row["id"]
                    if not conversation_id:
                        continue
                    raw_name = row["roomname_remark"] or row["name"] or ""
                    display_name = raw_name or _shared_name_from_conversation_id(
                        conversation_id,
                        user_map,
                        cfg["self_id"],
                    )
                    last_time = max(
                        int(row["last_message_time"] or 0),
                        last_times.get(conversation_id, 0),
                    )
                    conversations[conversation_id] = {
                        "conversation_id": conversation_id,
                        "display_name": display_name,
                        "kind": _shared_conversation_kind(conversation_id),
                        "message_count": counts.get(conversation_id, 0),
                        "last_time": last_time,
                        "last_message_id": int(row["last_message_id"] or 0),
                    }
        finally:
            conn.close()

    for conversation_id, count in counts.items():
        if conversation_id in conversations:
            conversations[conversation_id]["message_count"] = count
            conversations[conversation_id]["last_time"] = max(
                conversations[conversation_id]["last_time"],
                last_times.get(conversation_id, 0),
            )
            continue

        conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "display_name": _shared_name_from_conversation_id(
                conversation_id,
                user_map,
                cfg["self_id"],
            ),
            "kind": _shared_conversation_kind(conversation_id),
            "message_count": count,
            "last_time": last_times.get(conversation_id, 0),
            "last_message_id": 0,
        }

    result = [item for item in conversations.values() if item["message_count"] > 0]
    result.sort(key=lambda item: (item["last_time"], item["message_count"]), reverse=True)
    return result


def _validate_message_table(table: str) -> None:
    if table not in _MESSAGE_TABLES:
        raise ValueError(f"unsupported message table: {table}")


def _validate_limit(limit: int, *, maximum: int) -> int:
    if not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if limit <= 0:
        raise ValueError("limit must be greater than 0")
    if limit > maximum:
        raise ValueError(f"limit must be less than or equal to {maximum}")
    return limit


def _validate_offset(offset: int) -> int:
    if not isinstance(offset, int):
        raise ValueError("offset must be an integer")
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0")
    return offset


def _parse_time(value: str, *, is_end: bool) -> int:
    text = (value or "").strip()
    if not text:
        return 0

    normalized = text.replace("T", " ").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            return int(dt.timestamp())
        return int(dt.timestamp())
    except ValueError:
        pass

    for fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d" and is_end:
                dt = dt.replace(hour=23, minute=59, second=59)
            return int(dt.timestamp())
        except ValueError:
            continue

    raise ValueError(f"invalid time value: {value}")


def _parse_time_range(start_time: str, end_time: str) -> tuple[int | None, int | None]:
    start_ts = _parse_time(start_time, is_end=False) if start_time.strip() else None
    end_ts = _parse_time(end_time, is_end=True) if end_time.strip() else None
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise ValueError("start_time must be earlier than or equal to end_time")
    return start_ts, end_ts


def _iter_message_rows(
    message_db: str,
    *,
    conversation_ids: list[str] | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[sqlite3.Row]:
    conn = _open_db(message_db)
    rows: list[sqlite3.Row] = []
    try:
        for table in _MESSAGE_TABLES:
            _validate_message_table(table)
            if not _table_exists(conn, table):
                continue
            clauses: list[str] = []
            params: list[Any] = []
            if conversation_ids:
                placeholders = ",".join("?" for _ in conversation_ids)
                clauses.append(f"conversation_id IN ({placeholders})")
                params.extend(conversation_ids)
            if start_ts is not None:
                clauses.append("send_time >= ?")
                params.append(start_ts)
            if end_ts is not None:
                clauses.append("send_time <= ?")
                params.append(end_ts)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = (
                f'SELECT rowid AS source_rowid, "{table}" AS source_table, message_id, server_id, sequence, '
                f"sender_id, conversation_id, content_type, send_time, flag, "
                f"content, extra_content, local_extra_content "
                f'FROM "{table}" {where} '
                f"ORDER BY send_time DESC, sequence DESC, message_id DESC"
            )
            rows.extend(conn.execute(sql, params).fetchall())
    finally:
        conn.close()
    return rows


def _conversation_payload(conversation: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_name": conversation["display_name"],
        "conversation_id": conversation["conversation_id"],
        "conversation_type": conversation["kind"],
        "message_count": conversation["message_count"],
        "last_message_time": _shared_format_time(conversation["last_time"]),
        "last_message_timestamp": conversation["last_time"],
    }


def _message_payload(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation": message["conversation"],
        "conversation_id": message["conversation_id"],
        "conversation_type": message["conversation_kind"],
        "sender": message["sender"],
        "message_type": message["type_name"],
        "message_type_code": message["content_type"],
        "time": message["time"],
        "timestamp": message["send_time"],
        "content": message["display_content"],
    }


def _dedupe_and_build_messages(
    rows: list[sqlite3.Row],
    *,
    conv_map: dict[str, dict[str, Any]],
    user_map: dict[int, str],
    member_names: dict[str, dict[int, str]],
    self_id: int | None,
) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    built: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row["conversation_id"],
            row["message_id"],
            row["server_id"],
            row["sequence"],
        )
        if key in seen:
            continue
        seen.add(key)
        built.append(
            _shared_build_message(row, conv_map, user_map, member_names, self_id)
        )
    return built


def _page_latest(items: list[dict[str, Any]], *, limit: int, offset: int) -> list[dict[str, Any]]:
    page = items[offset:offset + limit]
    return list(reversed(page))


def _resolve_conversation(chat_name: str, conversations: list[dict[str, Any]]) -> dict[str, Any]:
    query = (chat_name or "").strip()
    if not query:
        raise ValueError("chat_name cannot be empty")

    conv_map = {item["conversation_id"]: item for item in conversations}
    if query in conv_map:
        return {"status": "ok", "conversation": conv_map[query]}

    exact = [
        item
        for item in conversations
        if item["display_name"].casefold() == query.casefold()
    ]
    if len(exact) == 1:
        return {"status": "ok", "conversation": exact[0]}
    if len(exact) > 1:
        return {
            "status": "ambiguous",
            "candidates": [_conversation_payload(item) for item in exact],
        }

    fuzzy = [
        item
        for item in conversations
        if query.casefold() in item["display_name"].casefold()
        or query.casefold() in item["conversation_id"].casefold()
    ]
    if len(fuzzy) == 1:
        return {"status": "ok", "conversation": fuzzy[0]}
    if len(fuzzy) > 1:
        return {
            "status": "ambiguous",
            "candidates": [_conversation_payload(item) for item in fuzzy],
        }

    return {"status": "not_found", "chat_name": query}


def get_recent_sessions(limit: int = 20) -> dict[str, Any]:
    limit = _validate_limit(limit, maximum=_MAX_RECENT_LIMIT)
    sessions = discover_conversations()
    return {
        "status": "ok",
        "sessions": [_conversation_payload(item) for item in sessions[:limit]],
    }


def get_chat_history(
    chat_name: str,
    limit: int = 20,
    offset: int = 0,
    start_time: str = "",
    end_time: str = "",
) -> dict[str, Any]:
    limit = _validate_limit(limit, maximum=_MAX_HISTORY_LIMIT)
    offset = _validate_offset(offset)
    start_ts, end_ts = _parse_time_range(start_time, end_time)
    decrypted_dir = _require_decrypted_dir()
    conversations = discover_conversations(decrypted_dir)
    resolved = _resolve_conversation(chat_name, conversations)
    if resolved["status"] != "ok":
        return resolved

    cfg = _load_config()
    user_map = _load_user_map(decrypted_dir)
    member_names = _load_group_member_names(decrypted_dir)
    conversation = resolved["conversation"]
    conv_map = {item["conversation_id"]: item for item in conversations}
    rows = _iter_message_rows(
        os.path.join(decrypted_dir, "message.db"),
        conversation_ids=[conversation["conversation_id"]],
        start_ts=start_ts,
        end_ts=end_ts,
    )
    messages = _dedupe_and_build_messages(
        rows,
        conv_map=conv_map,
        user_map=user_map,
        member_names=member_names,
        self_id=cfg["self_id"],
    )
    paged = _page_latest(messages, limit=limit, offset=offset)
    return {
        "status": "ok",
        "conversation": _conversation_payload(conversation),
        "messages": [_message_payload(item) for item in paged],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": len(messages),
            "has_more": offset + limit < len(messages),
        },
    }


def search_messages(
    keyword: str,
    chat_name: str = "",
    limit: int = 20,
    offset: int = 0,
    start_time: str = "",
    end_time: str = "",
) -> dict[str, Any]:
    keyword = (keyword or "").strip()
    if not keyword:
        raise ValueError("keyword cannot be empty")

    limit = _validate_limit(limit, maximum=_MAX_SEARCH_LIMIT)
    offset = _validate_offset(offset)
    start_ts, end_ts = _parse_time_range(start_time, end_time)
    decrypted_dir = _require_decrypted_dir()
    conversations = discover_conversations(decrypted_dir)
    conversation_ids: list[str] | None = None
    target_conversation: dict[str, Any] | None = None

    if chat_name.strip():
        resolved = _resolve_conversation(chat_name, conversations)
        if resolved["status"] != "ok":
            return resolved
        target_conversation = resolved["conversation"]
        conversation_ids = [target_conversation["conversation_id"]]

    cfg = _load_config()
    user_map = _load_user_map(decrypted_dir)
    member_names = _load_group_member_names(decrypted_dir)
    conv_map = {item["conversation_id"]: item for item in conversations}
    rows = _iter_message_rows(
        os.path.join(decrypted_dir, "message.db"),
        conversation_ids=conversation_ids,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    messages = _dedupe_and_build_messages(
        rows,
        conv_map=conv_map,
        user_map=user_map,
        member_names=member_names,
        self_id=cfg["self_id"],
    )
    matched = [
        item
        for item in messages
        if keyword.casefold() in item["display_content"].casefold()
    ]
    paged = _page_latest(matched, limit=limit, offset=offset)
    result: dict[str, Any] = {
        "status": "ok",
        "keyword": keyword,
        "messages": [_message_payload(item) for item in paged],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": len(matched),
            "has_more": offset + limit < len(matched),
        },
    }
    if target_conversation is not None:
        result["conversation"] = _conversation_payload(target_conversation)
    return result


def _normalize_contact_row(user_row: sqlite3.Row, relation_row: sqlite3.Row | None) -> dict[str, Any]:
    remarks = relation_row["remarks"] if relation_row else ""
    real_remarks = relation_row["real_remarks"] if relation_row else ""
    corp_remark = relation_row["corp_remark"] if relation_row else ""
    display_name = (
        real_remarks
        or remarks
        or corp_remark
        or user_row["real_name"]
        or user_row["name"]
        or user_row["account"]
        or str(user_row["id"])
    )
    return {
        "contact_id": int(user_row["id"]),
        "display_name": display_name,
        "name": user_row["name"] or "",
        "real_name": user_row["real_name"] or "",
        "account": user_row["account"] or "",
        "remark": remarks or "",
        "real_remark": real_remarks or "",
        "corp_remark": corp_remark or "",
        "external_corp_name": user_row["external_corp_name"] or "",
        "external_job": user_row["external_job"] or "",
    }


def get_contacts(query: str = "", limit: int = 50) -> dict[str, Any]:
    limit = _validate_limit(limit, maximum=_MAX_CONTACT_LIMIT)
    decrypted_dir = _require_decrypted_dir()
    user_db = os.path.join(decrypted_dir, "user.db")
    if not os.path.exists(user_db):
        raise FileNotFoundError("user.db does not exist")

    normalized_query = query.strip().casefold()
    contacts: list[dict[str, Any]] = []
    conn = _open_db(user_db)
    try:
        relation_rows: dict[int, sqlite3.Row] = {}
        if _table_exists(conn, "external_user_relation_v3"):
            relation_rows = {
                int(row["user_id"]): row
                for row in conn.execute(
                    "SELECT user_id, remarks, real_remarks, corp_remark "
                    "FROM external_user_relation_v3"
                )
            }
        for user_row in conn.execute(
            "SELECT id, name, real_name, account, external_corp_name, external_job "
            "FROM user_table ORDER BY id"
        ):
            contact = _normalize_contact_row(
                user_row,
                relation_rows.get(int(user_row["id"])),
            )
            haystack = [
                contact["display_name"],
                contact["name"],
                contact["real_name"],
                contact["account"],
                contact["remark"],
                contact["real_remark"],
                contact["corp_remark"],
                contact["external_corp_name"],
            ]
            if normalized_query and not any(
                normalized_query in str(value).casefold() for value in haystack if value
            ):
                continue
            contacts.append(contact)
    finally:
        conn.close()

    return {"status": "ok", "contacts": contacts[:limit]}


def get_new_messages(limit: int = 20) -> dict[str, Any]:
    limit = _validate_limit(limit, maximum=_MAX_HISTORY_LIMIT)
    decrypted_dir = _require_decrypted_dir()
    conversations = discover_conversations(decrypted_dir)
    cfg = _load_config()
    user_map = _load_user_map(decrypted_dir)
    member_names = _load_group_member_names(decrypted_dir)
    conv_map = {item["conversation_id"]: item for item in conversations}
    rows = _iter_message_rows(os.path.join(decrypted_dir, "message.db"))
    messages = _dedupe_and_build_messages(
        rows,
        conv_map=conv_map,
        user_map=user_map,
        member_names=member_names,
        self_id=cfg["self_id"],
    )
    paged = _page_latest(messages, limit=limit, offset=0)
    return {
        "status": "ok",
        "query_mode": "latest_messages_query",
        "note": "This tool queries the latest messages currently stored in the database. It is not an SSE listener.",
        "messages": [_message_payload(item) for item in paged],
    }


def get_messages_for_monitor(limit: int = 2000) -> list[dict[str, Any]]:
    return get_messages_for_monitor_incremental(limit=limit)


def build_monitor_cursor(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "send_time": int(message["send_time"] or 0),
        "sequence": int(message["sequence"] or 0),
        "message_id": int(message["message_id"] or 0),
        "source_rowid": int(message["source_rowid"] or 0),
        "source_table": str(message["source_table"] or ""),
    }


def get_messages_for_monitor_incremental(
    *,
    limit: int = 2000,
    after_cursor: dict[str, Any] | None = None,
    lookback_seconds: int = 120,
) -> list[dict[str, Any]]:
    limit = _validate_limit(limit, maximum=5000)
    decrypted_dir = _require_decrypted_dir()
    conversations = discover_conversations(decrypted_dir)
    cfg = _load_config()
    user_map = _load_user_map(decrypted_dir)
    member_names = _load_group_member_names(decrypted_dir)
    conv_map = {item["conversation_id"]: item for item in conversations}
    seen: set[tuple[Any, ...]] = set()
    normalized: list[dict[str, Any]] = []
    start_ts: int | None = None
    if after_cursor is not None:
        start_ts = max(0, int(after_cursor.get("send_time") or 0) - max(0, int(lookback_seconds or 0)))

    for raw_row in _iter_message_rows(
        os.path.join(decrypted_dir, "message.db"),
        start_ts=start_ts,
    ):
        if (
            after_cursor is not None
            and int(raw_row["message_id"] or 0) == int(after_cursor.get("message_id") or 0)
            and int(raw_row["sequence"] or 0) == int(after_cursor.get("sequence") or 0)
            and int(raw_row["send_time"] or 0) == int(after_cursor.get("send_time") or 0)
            and str(raw_row["source_table"] or "") == str(after_cursor.get("source_table") or "")
        ):
            continue
        dedupe_key = (
            raw_row["conversation_id"],
            raw_row["message_id"],
            raw_row["server_id"],
            raw_row["sequence"],
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        message = _shared_build_message(
            raw_row,
            conv_map,
            user_map,
            member_names,
            cfg["self_id"],
        )
        if message["is_sent"]:
            continue
        if message["content_type"] not in (0, 2):
            continue
        if not message["conversation_id"]:
            continue
        if not message["display_content"].strip():
            continue
        if int(message["sender_id"] or 0) <= 0:
            continue
        normalized.append(
            {
                "source_table": message["source_table"],
                "source_rowid": int(raw_row["source_rowid"] or 0),
                "conversation_id": message["conversation_id"],
                "conversation_name": message["conversation"],
                "conversation_type": message["conversation_kind"],
                "message_id": int(message["message_id"] or 0),
                "server_id": int(message["server_id"] or 0),
                "sequence": int(message["sequence"] or 0),
                "send_time": int(message["send_time"] or 0),
                "sender_id": str(message["sender_id"]),
                "sender_name": message["sender"],
                "content_type": int(message["content_type"] or 0),
                "content": message["display_content"],
                "content_summary": message["display_content"][:80],
                "time": message["time"],
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def get_messages_for_monitor(
    limit: int = 2000,
    after_cursor: dict[str, Any] | None = None,
    lookback_seconds: int = 120,
) -> list[dict[str, Any]]:
    return get_messages_for_monitor_incremental(
        limit=limit,
        after_cursor=after_cursor,
        lookback_seconds=lookback_seconds,
    )
