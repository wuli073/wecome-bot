from pathlib import Path
from tempfile import TemporaryDirectory

from src.langbot.pkg.utils import paths


def test_get_data_root_uses_source_root_in_repo_checkout():
    data_root = Path(paths.get_data_root())
    repo_root = Path(__file__).resolve().parents[2]

    assert data_root == repo_root / 'data'


def test_get_data_path_joins_under_data_root():
    data_path = Path(paths.get_data_path('skills', 'demo-skill'))
    repo_root = Path(__file__).resolve().parents[2]

    assert data_path == repo_root / 'data' / 'skills' / 'demo-skill'


def test_get_data_root_honors_env_override(monkeypatch):
    tmp_root = Path.cwd() / '.tmp-pytest'
    tmp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=tmp_root) as temp_dir:
        custom_data = Path(temp_dir) / 'custom-data'
        monkeypatch.setenv('LANGBOT_DATA_ROOT', str(custom_data))

        assert Path(paths.get_data_root()) == custom_data.resolve()


def test_get_repo_root_is_source_root_and_not_derived_from_data_root(monkeypatch):
    tmp_root = Path.cwd() / '.tmp-pytest'
    tmp_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=tmp_root) as temp_dir:
        custom_data = Path(temp_dir) / 'custom-data'
        monkeypatch.setenv('LANGBOT_DATA_ROOT', str(custom_data))

        repo_root = paths.get_repo_root()

        assert repo_root is not None
        assert Path(repo_root) == Path(__file__).resolve().parents[2]
        assert Path(repo_root) != custom_data.resolve().parent
