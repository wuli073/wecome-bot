import tempfile
import json
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
        request = json.loads(
            result_file.with_name("extract-result.request.json").read_text(encoding="utf-8")
        )
        result_file.write_text(
            json.dumps({"requestId": request["requestId"], "ok": True, "keys_file": "keys.json"}),
            encoding="utf-8",
        )
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

    assert payload["ok"] is True
    assert payload["keys_file"] == "keys.json"
    assert payload["requestId"]
    assert result_file.exists() is False
    assert result_file.with_name("extract-result.helper.ps1").exists() is False


@pytest.mark.asyncio
async def test_run_elevated_extract_uses_unique_absolute_json_ipc(tmp_path, monkeypatch) -> None:
    result_file = tmp_path / "extract-result.json"
    captured: dict = {}

    async def _fake_exec(*_args, **_kwargs):
        request_file = result_file.with_name("extract-result.request.json")
        captured["request"] = json.loads(request_file.read_text(encoding="utf-8"))
        result_file.write_text(
            json.dumps(
                {
                    "requestId": captured["request"]["requestId"],
                    "ok": True,
                    "keys_file": "keys.json",
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"", b"")))

    monkeypatch.setattr(uac_helper.asyncio, "create_subprocess_exec", AsyncMock(side_effect=_fake_exec))

    payload = await uac_helper.run_elevated_extract(
        python_exe=r"C:\\Program Files\\Chatbot\\connectors\\runtime\\python\\python.exe",
        connector_cli=tmp_path / "connector_cli.py",
        connector_name="wechat",
        runtime_dir=r"C:\\Users\\中文 用户 (test) & !\\AppData\\Local\\Chatbot\\connectors\\wechat-local",
        result_file=result_file,
    )

    request = captured["request"]
    assert payload == {"requestId": request["requestId"], "ok": True, "keys_file": "keys.json"}
    assert request["requestPath"].endswith("extract-result.request.json")
    assert request["resultPath"].endswith("extract-result.json")
    assert request["logPath"].endswith("extract-result.helper.log")
    assert Path(request["requestPath"]).is_absolute()
    assert Path(request["resultPath"]).is_absolute()
    assert Path(request["logPath"]).is_absolute()
    assert request["runtimeDir"].endswith("中文 用户 (test) & !\\AppData\\Local\\Chatbot\\connectors\\wechat-local")
    assert result_file.with_name("extract-result.request.json").exists() is False
    assert result_file.with_name("extract-result.helper.log").exists() is False


@pytest.mark.asyncio
async def test_run_elevated_extract_rejects_result_from_another_request(tmp_path, monkeypatch) -> None:
    result_file = tmp_path / "extract-result.json"

    async def _fake_exec(*_args, **_kwargs):
        result_file.write_text('{"requestId": "another-request", "ok": true}', encoding="utf-8")
        return SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"", b"")))

    monkeypatch.setattr(uac_helper.asyncio, "create_subprocess_exec", AsyncMock(side_effect=_fake_exec))

    payload = await uac_helper.run_elevated_extract(
        python_exe="python.exe",
        connector_cli=tmp_path / "connector_cli.py",
        connector_name="wxwork",
        runtime_dir=str(tmp_path),
        result_file=result_file,
    )

    assert payload["error_code"] == "RESULT_JSON_INVALID"


@pytest.mark.asyncio
async def test_run_elevated_extract_reports_helper_timeout(tmp_path, monkeypatch) -> None:
    fake_process = SimpleNamespace(returncode=None, communicate=AsyncMock(side_effect=TimeoutError))
    monkeypatch.setattr(uac_helper.asyncio, "create_subprocess_exec", AsyncMock(return_value=fake_process))

    payload = await uac_helper.run_elevated_extract(
        python_exe="python.exe",
        connector_cli=tmp_path / "connector_cli.py",
        connector_name="wxwork",
        runtime_dir=str(tmp_path),
        result_file=tmp_path / "extract-result.json",
        timeout_seconds=0.01,
    )

    assert payload["error_code"] == "HELPER_TIMEOUT"
