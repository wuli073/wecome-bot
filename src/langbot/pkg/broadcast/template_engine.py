from __future__ import annotations

import re


VARIABLE_PATTERN = re.compile(r'{{\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)\s*}}')


def extract_variables(content: str) -> list[str]:
    variables: list[str] = []
    seen: set[str] = set()
    for match in VARIABLE_PATTERN.finditer(content):
        variable = match.group(1).strip()
        if variable in seen:
            continue
        seen.add(variable)
        variables.append(variable)
    return variables


def render_template(content: str, variables: dict[str, object]) -> dict[str, object]:
    required_variables = extract_variables(content)
    missing_variables = [
        key for key in required_variables if str(variables.get(key, '')).strip() == ''
    ]

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = variables.get(key)
        if value is None or str(value).strip() == '':
            return match.group(0)
        return str(value)

    rendered_text = VARIABLE_PATTERN.sub(replace, content)
    return {
        'rendered_text': rendered_text,
        'required_variables': required_variables,
        'missing_variables': missing_variables,
        'valid': len(missing_variables) == 0,
    }
