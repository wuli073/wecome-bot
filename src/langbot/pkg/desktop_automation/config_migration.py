from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


LEGACY_RUNTIME_VERSION_FIELDS = frozenset({'expected_protocol_version', 'runtime_version'})
_DESKTOP_AUTOMATION_SECTION = re.compile(r'^(?P<indent>[ \t]*)desktop_automation\s*:\s*(?:#.*)?(?:\r?\n)?$')
_LEGACY_FIELD = re.compile(r'^(?P<indent>[ \t]*)(?P<name>expected_protocol_version|runtime_version)\s*:')


def remove_legacy_runtime_version_fields(config: dict[str, Any] | None) -> bool:
    """Remove retired Runtime version settings from an in-memory configuration."""
    if not isinstance(config, dict):
        return False
    desktop_automation = config.get('desktop_automation')
    if not isinstance(desktop_automation, dict):
        return False
    changed = False
    for field in LEGACY_RUNTIME_VERSION_FIELDS:
        if field in desktop_automation:
            desktop_automation.pop(field)
            changed = True
    return changed


def migrate_legacy_runtime_version_fields(config_path: str | Path) -> bool:
    """Delete only retired direct YAML fields while preserving the rest of the file verbatim."""
    path = Path(config_path)
    try:
        original_bytes = path.read_bytes()
    except FileNotFoundError:
        return False
    try:
        original = original_bytes.decode('utf-8')
        yaml.safe_load(original)
    except (UnicodeDecodeError, yaml.YAMLError):
        return False

    lines = original.splitlines(keepends=True)
    migrated: list[str] = []
    section_indent: int | None = None
    child_indent: int | None = None
    changed = False
    for line in lines:
        section_match = _DESKTOP_AUTOMATION_SECTION.match(line)
        if section_match:
            section_indent = len(section_match.group('indent').expandtabs(4))
            child_indent = None
            migrated.append(line)
            continue

        stripped = line.strip()
        indent = len(line) - len(line.lstrip(' \t'))
        if section_indent is not None and stripped and not stripped.startswith('#') and indent <= section_indent:
            section_indent = None
            child_indent = None

        if section_indent is not None and stripped and not stripped.startswith('#') and indent > section_indent:
            if child_indent is None or indent < child_indent:
                child_indent = indent

        field_match = _LEGACY_FIELD.match(line)
        if section_indent is not None and field_match and child_indent is not None:
            field_indent = len(field_match.group('indent').expandtabs(4))
            if child_indent == field_indent:
                changed = True
                continue
        migrated.append(line)

    if not changed:
        return False
    temporary_path = path.with_suffix(path.suffix + '.runtime-migration.tmp')
    try:
        temporary_path.write_bytes(''.join(migrated).encode('utf-8'))
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return True
