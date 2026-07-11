# wechat_decrypt release subset

This directory is the only releasable Connector source tree for the Windows trial release.

## Included

- CLI orchestration: `connector_cli.py`, `connector_runtime.py`
- MCP entrypoints confirmed by Task 1: `mcp_server.py`, `mcp_wxwork_server.py`
- WXWork monitor: `wxwork_message_monitor.py`
- Key extraction and decrypt helpers: `find_all_keys_windows.py`, `find_wxwork_keys.py`, `decrypt_db.py`, `decrypt_wxwork_db.py`
- Supporting modules required by the audited entrypoints
- Release metadata: `requirements.txt`, `README.release.md`, `source-manifest.json`

## Excluded by default

- HTTP wrapper entrypoints: `mcp_http_server.py`, `mcp_wxwork_http_server.py`
- Export / toolbox / legacy build helpers not required by the audited release scope
- Any desktop backup content outside `vendor/wechat_decrypt`

## Maintenance rules

1. Update `source-manifest.json` whenever the audited entrypoints, subprocess behavior, or required support files change.
2. Keep runtime outputs outside this source tree.
3. Treat desktop backup trees as audit references only; never package them directly.
4. Task 5 owns `requirements.lock.txt`; do not create it in Task 4.
