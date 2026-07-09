import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from langbot.pkg.local_connectors import uac_helper


def test_load_result_file_accepts_utf8_bom() -> None:
    base_dir = Path.cwd() / ".tmp-pytest"
    base_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base_dir) as temp_dir:
        result_file = Path(temp_dir) / "result.json"
        result_file.write_text('{"ok": true, "keys_file": "x"}', encoding="utf-8-sig")

        payload = uac_helper._load_result_file(result_file)

        assert payload == {"ok": True, "keys_file": "x"}


@pytest.mark.asyncio
async def test_run_elevated_extract_cleans_temp_files_after_uac_cancel(tmp_path, monkeypatch) -> None:
    result_file = tmp_path / "extract-result.json"

    fake_process = SimpleNamespace(
        returncode=1223,
        communicate=AsyncMock(return_value=(b"", b"")),
    )
    monkeypatch.setattr(
        uac_helper.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=fake_process),
    )

    payload = await uac_helper.run_elevated_extract(
        python_exe=r"C:\Program Files\Chatbot\connectors\runtime\python\python.exe",
        connector_cli=tmp_path / "connector_cli.py",
        connector_name="wechat",
        runtime_dir=r"C:\Users\测试 用户\AppData\Local\Chatbot\connectors\wechat-local",
        result_file=result_file,
    )

    assert payload["error_code"] == "UAC_CANCELLED"
    assert result_file.exists() is False
    assert result_file.with_suffix(".ps1").exists() is False


@pytest.mark.asyncio
async def test_run_elevated_extract_cleans_temp_files_after_success(tmp_path, monkeypatch) -> None:
    result_file = tmp_path / "extract-result.json"

    async def _fake_exec(*_args, **_kwargs):
        result_file.write_text('{"ok": true, "keys_file": "keys.json"}', encoding="utf-8")
        return SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b"", b"")),
        )

    monkeypatch.setattr(
        uac_helper.asyncio,
        "create_subprocess_exec",
        AsyncMock(side_effect=_fake_exec),
    )

    payload = await uac_helper.run_elevated_extract(
        python_exe=r"C:\Program Files\Chatbot\connectors\runtime\python\python.exe",
        connector_cli=tmp_path / "connector_cli.py",
        connector_name="wxwork",
        runtime_dir=r"C:\Users\测试 用户\AppData\Local\Chatbot\connectors\wxwork-local",
        result_file=result_file,
    )

    assert payload == {"ok": True, "keys_file": "keys.json"}
    assert result_file.exists() is False
    assert result_file.with_suffix(".ps1").exists() is False
