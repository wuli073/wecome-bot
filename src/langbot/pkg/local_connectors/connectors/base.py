from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from ..models import BuiltinConnectorDefinition


class BaseLocalConnector:
    def __init__(self, definition: BuiltinConnectorDefinition) -> None:
        self.definition = definition

    @property
    def connector_id(self) -> str:
        return self.definition.connector_id

    @property
    def expected_tool_names(self) -> tuple[str, ...]:
        raise NotImplementedError

    @property
    def server_script(self) -> str:
        raise NotImplementedError

    @property
    def monitor_script(self) -> str | None:
        return None

    @property
    def cli_connector_name(self) -> str:
        raise NotImplementedError

    @property
    def port(self) -> int:
        raise NotImplementedError

    def port_for_role(self, role: str) -> int | None:
        if role == "mcp":
            return self.port
        return None

    def resolve_decrypt_dir(self) -> Path:
        env_path = os.environ.get("WECOME_WECHAT_DECRYPT_DIR")
        candidates = []
        if env_path:
            candidates.append(Path(env_path))
        candidates.append(Path.cwd().parent / "wechat-decrypt")
        candidates.append(Path.home() / "Desktop" / "wechat-decrypt")
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        raise FileNotFoundError("wechat-decrypt directory not found; set WECOME_WECHAT_DECRYPT_DIR")

    def resolve_python_executable(self) -> str:
        decrypt_dir = self.resolve_decrypt_dir()
        windows_venv = decrypt_dir / ".venv" / "Scripts" / "python.exe"
        if windows_venv.exists():
            return str(windows_venv)
        return sys.executable

    async def run_cli(self, action: str, runtime_dir: str) -> dict:
        decrypt_dir = self.resolve_decrypt_dir()
        process = await asyncio.create_subprocess_exec(
            self.resolve_python_executable(),
            "-X",
            "utf8",
            str(decrypt_dir / "connector_cli.py"),
            self.cli_connector_name,
            action,
            "--runtime-dir",
            runtime_dir,
            "--json",
            cwd=str(decrypt_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
        try:
            return json.loads(stdout.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {
                "ok": False,
                "connector": self.cli_connector_name,
                "action": action,
                "error_code": "INVALID_JSON",
                "error_message": stdout.decode("utf-8", errors="replace"),
            }

    async def detect(self) -> dict:
        decrypt_dir = self.resolve_decrypt_dir()
        process = await asyncio.create_subprocess_exec(
            self.resolve_python_executable(),
            "-X",
            "utf8",
            str(decrypt_dir / "connector_cli.py"),
            self.cli_connector_name,
            "detect",
            "--json",
            cwd=str(decrypt_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
        try:
            return json.loads(stdout.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {
                "ok": False,
                "connector": self.cli_connector_name,
                "action": "detect",
                "error_code": "INVALID_JSON",
                "error_message": stdout.decode("utf-8", errors="replace"),
            }

    def build_start_command(self, role: str = "mcp", runtime_dir: str | None = None) -> list[str]:
        decrypt_dir = self.resolve_decrypt_dir()
        script_name = self.server_script if role == "mcp" else self.monitor_script
        if not script_name:
            raise ValueError(f"Role {role} is not supported by connector {self.connector_id}")
        return [
            self.resolve_python_executable(),
            "-X",
            "utf8",
            str(decrypt_dir / script_name),
        ]

    def build_start_env(self, runtime_dir: str, role: str = "mcp") -> dict[str, str]:
        env = os.environ.copy()
        env["WECHAT_DECRYPT_APP_DIR"] = str(Path(runtime_dir) / "config")
        env["WECHAT_DECRYPT_NONINTERACTIVE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def build_command_identity(self, runtime_dir: str, role: str = "mcp") -> dict[str, str]:
        decrypt_dir = self.resolve_decrypt_dir()
        script_name = self.server_script if role == "mcp" else self.monitor_script
        if not script_name:
            raise ValueError(f"Role {role} is not supported by connector {self.connector_id}")
        return {
            "script_path": str((decrypt_dir / script_name).resolve()),
            "python_executable": str(Path(self.resolve_python_executable()).resolve()),
            "app_dir": str((Path(runtime_dir) / "config").resolve()),
        }
