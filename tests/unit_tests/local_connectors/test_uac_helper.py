import tempfile
from pathlib import Path

from langbot.pkg.local_connectors import uac_helper


def test_load_result_file_accepts_utf8_bom() -> None:
    base_dir = Path.cwd() / ".tmp-pytest"
    base_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base_dir) as temp_dir:
        result_file = Path(temp_dir) / "result.json"
        result_file.write_text('{"ok": true, "keys_file": "x"}', encoding="utf-8-sig")

        payload = uac_helper._load_result_file(result_file)

        assert payload == {"ok": True, "keys_file": "x"}
