import os
from pathlib import Path

from langbot.pkg.desktop_automation.config_migration import (
    migrate_legacy_runtime_version_fields,
    remove_legacy_runtime_version_fields,
)


def test_legacy_runtime_version_migration_removes_only_direct_fields_and_preserves_bytes(tmp_path):
    config_path = tmp_path / 'config.yaml'
    original = (
        "# global comment\r\napi:\r\n  expected_protocol_version: keep-api\r\n"
        "desktop_automation: # keep section comment\r\n  # keep before\r\n"
        "  expected_protocol_version: '1' # removed with field\r\n  enabled: true\r\n"
        "  nested:\r\n    runtime_version: keep-nested\r\n  # keep between\r\n"
        '  runtime_version: "0.1.1"\r\n  task_timeout_seconds: 120\r\n'
        "other:\r\n    runtime_version: keep-other\r\n"
    )
    config_path.write_bytes(original.encode('utf-8'))

    assert migrate_legacy_runtime_version_fields(config_path) is True
    assert config_path.read_bytes() == (
        "# global comment\r\napi:\r\n  expected_protocol_version: keep-api\r\n"
        "desktop_automation: # keep section comment\r\n  # keep before\r\n  enabled: true\r\n"
        "  nested:\r\n    runtime_version: keep-nested\r\n  # keep between\r\n"
        "  task_timeout_seconds: 120\r\nother:\r\n    runtime_version: keep-other\r\n"
    ).encode('utf-8')
    assert migrate_legacy_runtime_version_fields(config_path) is False


def test_legacy_runtime_version_migration_handles_lf_four_space_indent_and_unquoted_value(tmp_path):
    config_path = tmp_path / 'config.yaml'
    original = (
        "desktop_automation:\n    runtime_version: 0.1.1\n    enabled: true\n"
        "other:\n    expected_protocol_version: keep\n# expected_protocol_version in comment\n"
    )
    config_path.write_text(original, encoding='utf-8', newline='')

    assert migrate_legacy_runtime_version_fields(config_path) is True
    assert config_path.read_text(encoding='utf-8') == (
        "desktop_automation:\n    enabled: true\nother:\n    expected_protocol_version: keep\n"
        "# expected_protocol_version in comment\n"
    )


def test_legacy_runtime_version_migration_does_not_rewrite_missing_or_malformed_files(tmp_path):
    missing_path = tmp_path / 'missing.yaml'
    assert migrate_legacy_runtime_version_fields(missing_path) is False

    config_path = tmp_path / 'malformed.yaml'
    original = b'desktop_automation:\n  expected_protocol_version: 2\n  invalid: [\n'
    config_path.write_bytes(original)
    assert migrate_legacy_runtime_version_fields(config_path) is False
    assert config_path.read_bytes() == original


def test_legacy_runtime_version_migration_keeps_original_when_atomic_replace_fails(tmp_path, monkeypatch):
    config_path = tmp_path / 'config.yaml'
    original = b'desktop_automation:\n  expected_protocol_version: 2\n  enabled: true\n'
    config_path.write_bytes(original)

    def fail_replace(source, destination):
        raise OSError('replace failed')

    monkeypatch.setattr(os, 'replace', fail_replace)
    try:
        migrate_legacy_runtime_version_fields(config_path)
    except OSError as exc:
        assert str(exc) == 'replace failed'
    else:
        raise AssertionError('atomic replacement failure must be visible to the caller')
    assert config_path.read_bytes() == original
    assert not (tmp_path / 'config.yaml.runtime-migration.tmp').exists()


def test_in_memory_defaults_ignore_legacy_runtime_version_fields_without_touching_other_values():
    config = {
        'desktop_automation': {
            'enabled': True,
            'expected_protocol_version': '1',
            'runtime_version': '0.1.1',
            'task_timeout_seconds': 42,
        },
        'connectors': ['keep-me'],
    }

    assert remove_legacy_runtime_version_fields(config) is True
    assert config == {
        'desktop_automation': {'enabled': True, 'task_timeout_seconds': 42},
        'connectors': ['keep-me'],
    }
