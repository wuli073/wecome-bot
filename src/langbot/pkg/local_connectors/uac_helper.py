from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path


DEFAULT_HELPER_TIMEOUT_SECONDS = 120.0


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def _load_result_file(result_file: Path) -> dict:
    payload = json.loads(result_file.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Elevated helper result must be a JSON object")
    return payload


def _error(connector_name: str, code: str, message: str) -> dict:
    return {
        "ok": False,
        "connector": connector_name,
        "action": "extract-key",
        "error_code": code,
        "error_message": message,
    }


def _build_helper_script(request_file: Path) -> str:
    quoted_request_file = _ps_quote(str(request_file))
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$request = Get-Content -LiteralPath '{quoted_request_file}' -Raw -Encoding UTF8 | ConvertFrom-Json",
            "$stdoutPath = \"$($request.resultPath).stdout.$PID\"",
            "$stderrPath = \"$($request.resultPath).stderr.$PID\"",
            "$tempResultPath = \"$($request.resultPath).tmp.$PID.$([Guid]::NewGuid().ToString('N'))\"",
            "function Write-HelperLog([string]$Message) {",
            "  Add-Content -LiteralPath $request.logPath -Value $Message -Encoding UTF8",
            "}",
            "function Write-HelperResult($Payload) {",
            "  $Payload | ConvertTo-Json -Compress -Depth 8 | Set-Content -LiteralPath $tempResultPath -Encoding UTF8",
            "  Move-Item -LiteralPath $tempResultPath -Destination $request.resultPath -Force",
            "}",
            "try {",
            "  Write-HelperLog ('helper_started requestId=' + $request.requestId)",
            "  & $request.pythonExecutable -u -X utf8 $request.connectorCli $request.connector extract-key --runtime-dir $request.runtimeDir --json 1> $stdoutPath 2> $stderrPath",
            "  $exitCode = $LASTEXITCODE",
            "  $rawResult = Get-Content -LiteralPath $stdoutPath -Raw -Encoding UTF8",
            "  try { $result = $rawResult | ConvertFrom-Json -ErrorAction Stop }",
            "  catch {",
            "    $code = if ($exitCode -eq 0) { 'RESULT_JSON_INVALID' } else { 'HELPER_EXITED_WITH_ERROR' }",
            "    $result = [ordered]@{ requestId=$request.requestId; ok=$false; connector=$request.connector; action='extract-key'; error_code=$code; error_message='Elevated helper did not receive a valid connector result' }",
            "  }",
            "  if ($result.PSObject.Properties.Name -notcontains 'requestId') { $result | Add-Member -NotePropertyName requestId -NotePropertyValue $request.requestId } else { $result.requestId = $request.requestId }",
            "  Write-HelperResult $result",
            "  Write-HelperLog ('helper_completed requestId=' + $request.requestId + ' exitCode=' + $exitCode)",
            "  exit $exitCode",
            "}",
            "catch {",
            "  try {",
            "    Write-HelperLog ('helper_failed requestId=' + $request.requestId + ' type=' + $_.Exception.GetType().Name)",
            "    Write-HelperResult ([ordered]@{ requestId=$request.requestId; ok=$false; connector=$request.connector; action='extract-key'; error_code='HELPER_EXITED_WITH_ERROR'; error_message='Elevated helper failed before key extraction completed' })",
            "  } catch {}",
            "  exit 1",
            "}",
            "finally {",
            "  Remove-Item -LiteralPath $stdoutPath, $stderrPath, $tempResultPath -Force -ErrorAction SilentlyContinue",
            "}",
        ]
    )


async def run_elevated_extract(
    python_exe: str,
    connector_cli: Path,
    connector_name: str,
    runtime_dir: str,
    result_file: Path,
    *,
    timeout_seconds: float = DEFAULT_HELPER_TIMEOUT_SECONDS,
) -> dict:
    result_file = result_file.resolve()
    request_file = result_file.with_name(f"{result_file.stem}.request.json")
    log_file = result_file.with_name(f"{result_file.stem}.helper.log")
    helper_script = result_file.with_name(f"{result_file.stem}.helper.ps1")
    request_id = uuid.uuid4().hex
    result_file.parent.mkdir(parents=True, exist_ok=True)
    request = {
        "requestId": request_id,
        "connector": connector_name,
        "pythonExecutable": str(Path(python_exe).resolve()),
        "connectorCli": str(connector_cli.resolve()),
        "runtimeDir": str(Path(runtime_dir).resolve()),
        "requestPath": str(request_file),
        "resultPath": str(result_file),
        "logPath": str(log_file),
    }
    request_file.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    helper_script.write_text(_build_helper_script(request_file), encoding="utf-8")

    outer_command = " ".join(
        [
            "try {",
            "$process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden",
            f"-ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File','\"{_ps_quote(str(helper_script))}\"')",
            "-Wait -PassThru; exit $process.ExitCode",
            "} catch {",
            "if (($_.Exception.HResult -band 0xFFFF) -eq 1223) { exit 1223 }",
            "throw",
            "}",
        ]
    )

    process = None
    timed_out = False
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                outer_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            return _error(connector_name, "HELPER_START_FAILED", "Unable to start the elevated helper")

        try:
            await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            timed_out = True
            if hasattr(process, "kill"):
                process.kill()
            return _error(connector_name, "HELPER_TIMEOUT", "Elevated helper timed out")

        if process.returncode == 1223:
            return _error(connector_name, "UAC_CANCELLED", "UAC was cancelled")
        if not result_file.exists():
            code = "HELPER_EXITED_WITH_ERROR" if process.returncode else "RESULT_FILE_MISSING"
            return _error(connector_name, code, "Elevated helper did not produce a result file")
        try:
            result = _load_result_file(result_file)
        except (OSError, ValueError, json.JSONDecodeError):
            return _error(connector_name, "RESULT_JSON_INVALID", "Elevated helper returned invalid JSON")
        if result.get("requestId") != request_id:
            return _error(connector_name, "RESULT_JSON_INVALID", "Elevated helper result requestId did not match")
        if process.returncode and result.get("ok"):
            return _error(connector_name, "HELPER_EXITED_WITH_ERROR", "Elevated helper exited with an error")
        return result
    finally:
        if timed_out and process is not None and hasattr(process, "returncode") and process.returncode is None:
            try:
                await process.communicate()
            except Exception:
                pass
        for path in (result_file, request_file, log_file, helper_script):
            if path.exists():
                path.unlink()
