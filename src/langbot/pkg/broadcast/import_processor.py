from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .errors import (
    BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
    BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID,
    BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE,
)


UPLOAD_GROUP_FIELD_USERNAME = "用户名"
UPLOAD_GROUP_FIELD_ALIASES = (
    "用户名",
    "用户名称",
    "客户名称",
    "客户名",
    "客户",
    "姓名",
    "昵称",
)

GROUP_FIELD_SOURCE_USER_CONFIRMED = "user_confirmed"
GROUP_FIELD_SOURCE_AUTO_DETECTED = "auto_detected"
GROUP_FIELD_SOURCE_CONFIGURED = "configured"
GROUP_FIELD_SOURCE_LEGACY_FALLBACK = "legacy_fallback"
GROUP_FIELD_RUNTIME_SOURCES = {
    GROUP_FIELD_SOURCE_USER_CONFIRMED,
    GROUP_FIELD_SOURCE_AUTO_DETECTED,
    GROUP_FIELD_SOURCE_CONFIGURED,
    GROUP_FIELD_SOURCE_LEGACY_FALLBACK,
}

IMPORT_GROUP_FIELD_REQUIRED_MESSAGE = "请先设置客户分组字段后再导入文件"
IMPORT_FIELDS_MISSING_MESSAGE_PREFIX = "导入文件缺少以下字段："
REMATCH_FIELDS_MISSING_MESSAGE_PREFIX = "当前导入数据缺少以下字段，无法重新匹配："
UNMATCHED_GROUP_MESSAGE = "未匹配到群聊"
GROUP_FIELD_CONFIRMATION_REQUIRED_AMBIGUOUS_MESSAGE = "导入文件存在多个可能的客户分组字段，请确认后再继续"
GROUP_FIELD_CONFIRMATION_REQUIRED_UNRESOLVED_MESSAGE = "未识别到可唯一确定的客户分组字段，请用户确认后继续"


@dataclass(slots=True)
class BroadcastImportProcessorError(Exception):
    message: str
    code: str | None = None
    details: Any = None

    def __str__(self) -> str:
        return self.message


def resolve_upload_group_field(
    *,
    headers: list[str],
    variable_profile: dict[str, Any] | Any,
    group_field_override: str | None = None,
) -> dict[str, str]:
    header_candidates = _build_header_candidates(headers)
    exact_headers = [item["header"] for item in header_candidates]
    exact_header_set = set(exact_headers)

    override = _normalize_required_field(group_field_override)
    configured_group_field = _normalize_required_field(_get_value(variable_profile, "group_field")) or None
    if override:
        if override not in exact_header_set:
            raise BroadcastImportProcessorError(
                f"指定的客户分组字段不存在：{override}",
                code=BROADCAST_IMPORT_GROUP_FIELD_OVERRIDE_INVALID,
                details={
                    "group_field_override": override,
                    "headers": exact_headers,
                    "original_file_name": None,
                },
            )
        return {"group_field": override, "source": GROUP_FIELD_SOURCE_USER_CONFIRMED}

    username_header = next(
        (
            item["header"]
            for item in header_candidates
            if item["normalized_header"] == UPLOAD_GROUP_FIELD_USERNAME
        ),
        None,
    )
    if username_header is not None:
        return {"group_field": username_header, "source": GROUP_FIELD_SOURCE_AUTO_DETECTED}

    if configured_group_field and configured_group_field in exact_header_set:
        return {"group_field": configured_group_field, "source": GROUP_FIELD_SOURCE_CONFIGURED}

    alias_hits = [
        item["header"]
        for item in header_candidates
        if item["normalized_header"] in UPLOAD_GROUP_FIELD_ALIASES
    ]
    if len(alias_hits) == 1:
        return {"group_field": alias_hits[0], "source": GROUP_FIELD_SOURCE_AUTO_DETECTED}

    if alias_hits:
        raise BroadcastImportProcessorError(
            GROUP_FIELD_CONFIRMATION_REQUIRED_AMBIGUOUS_MESSAGE,
            code=BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
            details={
                "headers": exact_headers,
                "candidates": alias_hits,
                "configured_group_field": configured_group_field,
                "original_file_name": None,
            },
        )

    raise BroadcastImportProcessorError(
        GROUP_FIELD_CONFIRMATION_REQUIRED_UNRESOLVED_MESSAGE,
        code=BROADCAST_IMPORT_GROUP_FIELD_CONFIRMATION_REQUIRED,
        details={
            "headers": exact_headers,
            "candidates": [],
            "configured_group_field": configured_group_field,
            "original_file_name": None,
        },
    )


def resolve_persisted_batch_group_field(
    *,
    batch: dict[str, Any] | Any,
    variable_profile: dict[str, Any] | Any,
) -> dict[str, str]:
    batch_group_field = _normalize_required_field(_get_value(batch, "group_field_used"))
    if batch_group_field:
        return {
            "group_field": batch_group_field,
            "source": _normalize_runtime_group_field_source(_get_value(batch, "group_field_source")),
        }

    configured_group_field = _normalize_required_field(_get_value(variable_profile, "group_field"))
    if configured_group_field:
        return {"group_field": configured_group_field, "source": GROUP_FIELD_SOURCE_LEGACY_FALLBACK}

    raise BroadcastImportProcessorError(
        "当前导入批次无法确定客户分组字段",
        code=BROADCAST_IMPORT_GROUP_FIELD_UNRESOLVABLE,
    )


def validate_import_headers(*, headers: list[str], variable_profile: dict[str, Any]) -> None:
    group_field = _normalize_required_field(variable_profile.get("group_field"))
    if not group_field:
        raise BroadcastImportProcessorError(IMPORT_GROUP_FIELD_REQUIRED_MESSAGE)

    missing_fields = _find_missing_fields(headers, variable_profile, include_group_field=True)
    if missing_fields:
        raise BroadcastImportProcessorError(
            f"{IMPORT_FIELDS_MISSING_MESSAGE_PREFIX}{'、'.join(missing_fields)}"
        )


def validate_rematch_headers(*, headers: list[str], variable_profile: dict[str, Any]) -> None:
    group_field = _normalize_required_field(variable_profile.get("group_field"))
    if not group_field:
        raise BroadcastImportProcessorError(IMPORT_GROUP_FIELD_REQUIRED_MESSAGE)

    missing_fields = _find_missing_fields(headers, variable_profile, include_group_field=True)
    if missing_fields:
        raise BroadcastImportProcessorError(
            f"{REMATCH_FIELDS_MISSING_MESSAGE_PREFIX}{'、'.join(missing_fields)}"
        )


def classify_import_rows(
    *,
    rows: list[dict[str, Any]],
    group_field: str,
    match_resolver: Callable[[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    classified_rows: list[dict[str, Any]] = []
    normalized_group_field = _normalize_required_field(group_field)

    for row in rows:
        raw_data = dict(row["raw_data"])
        group_value = str(raw_data.get(normalized_group_field) or "").strip()
        classified_row = {
            "source_row_number": row["source_row_number"],
            "raw_data": raw_data,
            "group_value": group_value or None,
            "matched_conversation_id": None,
            "matched_conversation_name": None,
            "matched_rule_id": None,
            "match_status": "invalid",
            "error_message": None,
        }

        if not group_value:
            classified_rows.append(classified_row)
            continue

        match_result = match_resolver(group_value)
        if bool(match_result.get("matched")):
            classified_row.update(
                {
                    "group_value": group_value,
                    "matched_conversation_id": match_result.get("matched_conversation_id"),
                    "matched_conversation_name": match_result.get("matched_conversation_name"),
                    "matched_rule_id": match_result.get("matched_rule_id"),
                    "match_status": "matched",
                    "error_message": None,
                }
            )
        else:
            classified_row.update(
                {
                    "group_value": group_value,
                    "match_status": "unmatched",
                    "error_message": UNMATCHED_GROUP_MESSAGE,
                }
            )

        classified_rows.append(classified_row)

    return classified_rows


def calculate_batch_stats(classified_rows: list[dict[str, Any]]) -> dict[str, int]:
    total_rows = len(classified_rows)
    invalid_rows = sum(1 for row in classified_rows if row["match_status"] == "invalid")
    matched_rows = sum(1 for row in classified_rows if row["match_status"] == "matched")
    unmatched_rows = sum(1 for row in classified_rows if row["match_status"] == "unmatched")
    valid_rows = matched_rows + unmatched_rows

    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
    }


def _find_missing_fields(
    headers: list[str],
    variable_profile: dict[str, Any],
    *,
    include_group_field: bool,
) -> list[str]:
    normalized_headers = {_normalize_required_field(header) for header in headers}
    required_fields: list[str] = []

    if include_group_field:
        group_field = _normalize_required_field(variable_profile.get("group_field"))
        if group_field:
            required_fields.append(group_field)

    for rule in variable_profile.get("mapping_rules") or []:
        source_field = _normalize_required_field(rule.get("source_field"))
        if source_field:
            required_fields.append(source_field)

    missing_fields: list[str] = []
    seen: set[str] = set()
    for field_name in required_fields:
        if field_name in seen:
            continue
        seen.add(field_name)
        if field_name not in normalized_headers:
            missing_fields.append(field_name)

    return missing_fields


def _normalize_required_field(value: Any) -> str:
    return str(value or "").strip()


def _normalize_upload_header(value: Any) -> str:
    return _normalize_required_field(value).lstrip("﻿")


def _build_header_candidates(headers: list[str]) -> list[dict[str, str]]:
    return [
        {
            "header": str(header or ""),
            "normalized_header": _normalize_upload_header(header),
        }
        for header in headers
    ]


def _get_value(container: dict[str, Any] | Any, key: str) -> Any:
    if isinstance(container, dict):
        return container.get(key)
    return getattr(container, key, None)


def _normalize_runtime_group_field_source(value: Any) -> str:
    source = _normalize_required_field(value)
    if source in GROUP_FIELD_RUNTIME_SOURCES:
        return source
    return GROUP_FIELD_SOURCE_CONFIGURED
