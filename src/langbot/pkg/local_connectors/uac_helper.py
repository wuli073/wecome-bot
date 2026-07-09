from __future__ import annotations

import asyncio
import json
from pathlib import Path


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def _load_result_file(result_file: Path) -> dict:
    return json.loads(result_file.read_text(encoding="utf-8-sig"))


async def run_elevated_extract(
    python_exe: str,
    connector_cli: Path,
    connector_name: str,
    runtime_dir: str,
    result_file: Path,
):
    result_file.parent.mkdir(parents=True, exist_ok=True)
    helper_script = result_file.with_suffix(".ps1")
    helper_script.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                (
                    f"& '{_ps_quote(python_exe)}' -X utf8 '{_ps_quote(str(connector_cli))}' "
                    f"{connector_name} extract-key --runtime-dir '{_ps_quote(runtime_dir)}' --json "
                    f"| Set-Content -LiteralPath '{_ps_quote(str(result_file))}' -Encoding UTF8"
                ),
            ]
        ),
        encoding="utf-8",
    )

    outer_command = (
        "try { "
        "$process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden "
        f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','{_ps_quote(str(helper_script))}') "
        "-Wait -PassThru; "
        "exit $process.ExitCode "
        "} catch { "
        "if (($_.Exception.HResult -band 0xFFFF) -eq 1223) { exit 1223 } "
        "throw "
        "}"
    )

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-Command",
            outer_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
    finally:
        if helper_script.exists():
            helper_script.unlink()
    try:
        if process is not None and process.returncode == 1223:
            return {
                "ok": False,
                "connector": connector_name,
                "action": "extract-key",
                "error_code": "UAC_CANCELLED",
                "error_message": "UAC was cancelled",
            }
        if not result_file.exists():
            return {
                "ok": False,
                "connector": connector_name,
                "action": "extract-key",
                "error_code": "KEY_EXTRACTION_FAILED",
                "error_message": "Elevated helper did not produce a result",
            }
        return _load_result_file(result_file)
    finally:
        if result_file.exists():
            result_file.unlink()
