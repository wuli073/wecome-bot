import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCKS = [
    ROOT / 'packaging' / 'server' / 'requirements.lock.txt',
    ROOT / 'vendor' / 'wechat_decrypt' / 'requirements.lock.txt',
]
FORBIDDEN = {'pytest', 'ruff', 'mypy', 'pre-commit', 'uv'}
NAME_RE = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[|==|~=|!=|<=|>=|<|>|===|@|;|\s|$)')


def canonicalize_name(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def iter_requirement_names(lock_path: Path):
    for line_number, raw_line in enumerate(lock_path.read_text(encoding='utf-8').splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.endswith('\'):
            line = line[:-1].rstrip()
        if line.startswith('-'):
            continue
        line = line.split(' #', 1)[0].strip()
        match = NAME_RE.match(line)
        if not match:
            raise SystemExit(f'cannot parse requirement name in {lock_path}:{line_number}: {raw_line}')
        yield canonicalize_name(match.group(1))


for lock_path in LOCKS:
    if not lock_path.exists():
        raise SystemExit(f'missing lock file: {lock_path}')
    names = set(iter_requirement_names(lock_path))
    forbidden_found = names & FORBIDDEN
    if forbidden_found:
        raise SystemExit(f'forbidden package names {sorted(forbidden_found)} found in {lock_path}')
print('dependency locks verified')
