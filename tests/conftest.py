import pytest


@pytest.fixture(autouse=True)
def isolated_project_registry(tmp_path, monkeypatch):
    """Tests and their child servers must never change the user's registry."""
    monkeypatch.setenv('LOOKING_GLASS_CONFIG_DIR', str(tmp_path/'user-config'))
