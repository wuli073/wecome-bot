from __future__ import annotations

import os
import shutil
import sys

import yaml

from ...desktop_automation.runtime_process import resolve_runtime_executable_path


required_files = {
    'data/config.yaml': 'templates/config.yaml',
}

required_paths = [
    'temp',
    'data',
    'data/metadata',
    'data/logs',
    'data/labels',
]


async def generate_files() -> list[str]:
    global required_files, required_paths

    from ...utils import paths as path_utils

    for required_path in required_paths:
        os.makedirs(required_path, exist_ok=True)

    generated_files = []
    for file in required_files:
        if not os.path.exists(file):
            template_path = path_utils.get_resource_path(required_files[file])
            shutil.copyfile(template_path, file)
            _apply_local_desktop_automation_defaults(file)
            generated_files.append(file)

    return generated_files


def _apply_local_desktop_automation_defaults(path: str) -> None:
    if path != 'data/config.yaml' or sys.platform != 'win32':
        return
    if resolve_runtime_executable_path() is None:
        return
    with open(path, encoding='utf-8') as file:
        config = yaml.safe_load(file) or {}
    desktop_automation = dict(config.get('desktop_automation') or {})
    if desktop_automation.get('enabled') is True:
        return
    desktop_automation['enabled'] = True
    config['desktop_automation'] = desktop_automation
    with open(path, 'w', encoding='utf-8') as file:
        yaml.safe_dump(config, file, allow_unicode=True, sort_keys=False)
