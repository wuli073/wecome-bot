from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import DesktopAutomationError, RUNTIME_CONTRACT_INVALID, RUNTIME_CONTRACT_UNAVAILABLE


@dataclass(frozen=True)
class RuntimeContract:
    """Version contract published with the trusted Desktop Runtime release."""

    protocol_version: str
    runtime_version: str
    tag: str


def runtime_descriptor_path(runtime_root: str | Path) -> Path:
    return Path(runtime_root) / 'distribution' / 'runtime' / 'desktop-runtime-release.json'


def load_runtime_contract(runtime_root: str | Path) -> RuntimeContract:
    """Load the local Runtime contract without consulting user configuration."""
    descriptor_path = runtime_descriptor_path(runtime_root)
    try:
        descriptor_text = descriptor_path.read_text(encoding='utf-8')
    except FileNotFoundError as exc:
        raise DesktopAutomationError(
            RUNTIME_CONTRACT_UNAVAILABLE,
            f'Desktop Runtime contract is unavailable: {descriptor_path}',
        ) from exc
    except OSError as exc:
        raise DesktopAutomationError(
            RUNTIME_CONTRACT_UNAVAILABLE,
            f'Desktop Runtime contract cannot be read: {descriptor_path}',
        ) from exc

    try:
        descriptor: Any = json.loads(descriptor_text)
    except json.JSONDecodeError as exc:
        raise DesktopAutomationError(
            RUNTIME_CONTRACT_INVALID,
            f'Desktop Runtime contract is not valid JSON: {descriptor_path}',
        ) from exc

    if not isinstance(descriptor, dict):
        raise DesktopAutomationError(RUNTIME_CONTRACT_INVALID, 'Desktop Runtime contract must be a JSON object')
    if descriptor.get('release_available') is not True:
        raise DesktopAutomationError(
            RUNTIME_CONTRACT_UNAVAILABLE,
            'Desktop Runtime contract does not declare an available release',
        )

    values: dict[str, str] = {}
    for field in ('protocol_version', 'runtime_version', 'tag'):
        value = descriptor.get(field)
        normalized = str(value).strip() if value is not None else ''
        if not normalized:
            raise DesktopAutomationError(
                RUNTIME_CONTRACT_INVALID,
                f'Desktop Runtime contract field is missing or empty: {field}',
            )
        values[field] = normalized

    return RuntimeContract(
        protocol_version=values['protocol_version'],
        runtime_version=values['runtime_version'],
        tag=values['tag'],
    )
