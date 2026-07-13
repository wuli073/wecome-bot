from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def test_release_manifest_cites_task1_confirmed_entrypoints():
    root = Path(__file__).resolve().parents[2] / 'vendor' / 'wechat_decrypt'
    manifest = json.loads((root / 'source-manifest.json').read_text(encoding='utf-8'))

    expected = {
        'connector_cli.py',
        'connector_runtime.py',
        'mcp_server.py',
        'mcp_wxwork_server.py',
        'wxwork_message_monitor.py',
        'find_all_keys_windows.py',
        'find_wxwork_keys.py',
        'decrypt_db.py',
        'decrypt_wxwork_db.py',
    }
    assert set(manifest['releaseScope']['includedRuntimeEntrypoints']) == expected
    assert 'mcp_http_server.py' in manifest['releaseScope']['excludedByDefault']
    assert manifest['task1BaselineReference'].endswith('trial-baseline-investigation.md')


def test_requirements_file_lists_runtime_direct_dependencies_only():
    root = Path(__file__).resolve().parents[2] / 'vendor' / 'wechat_decrypt'
    requirements = {
        line.strip() for line in (root / 'requirements.txt').read_text(encoding='utf-8').splitlines() if line.strip()
    }

    assert requirements == {
        'mcp>=1.25.0',
        'pycryptodome>=3.22.0',
        'zstandard>=0.25.0',
    }


def test_runtime_layout_stays_under_absolute_runtime_root():
    import connector_runtime

    with tempfile.TemporaryDirectory() as runtime_dir:
        layout = connector_runtime.ensure_runtime_layout(runtime_dir)

    root = Path(layout['runtime_root']).resolve()
    for key in ('app_dir', 'secrets_dir', 'decrypted_dir', 'logs_dir', 'jobs_dir', 'config_file'):
        path = Path(layout[key]).resolve()
        assert str(path).startswith(str(root))


def test_runtime_dir_rejects_file_path():
    import connector_runtime

    with tempfile.TemporaryDirectory() as temp_dir:
        marker = Path(temp_dir) / 'marker.txt'
        marker.write_text('x', encoding='utf-8')
        try:
            connector_runtime.resolve_runtime_dir(str(marker))
        except ValueError as exc:
            assert 'directory path' in str(exc)
        else:
            raise AssertionError('expected ValueError for file runtime_dir')
