"""Explorer ignore rules must take effect before traversal and the file cap."""
from pathlib import Path

import pytest

from looking_glass.app import create_app
from looking_glass.workspace import EXCLUDED, Problem, Workspace


def write(root, name, content='content\n'):
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding='utf-8')


@pytest.mark.parametrize('rules,hidden,visible', [
    ('outputs/\n', ['outputs/run.txt', 'src/outputs/run.txt'], ['src/main.py', 'outputs.txt']),
    ('/outputs/\n', ['outputs/run.txt'], ['src/outputs/run.txt', 'src/main.py']),
    ('*.log\n', ['run.log', 'src/run.log'], ['src/main.py', 'log.txt']),
    ('/run.log\n', ['run.log'], ['src/run.log']),
    ('src/generated\n', ['src/generated/run.py'], ['other/src/generated/run.py']),
    ('**/cache/**\n', ['cache/a.txt', 'src/cache/deep/a.txt'], ['src/main.py']),
    ('run?.[ch]\n', ['run1.c', 'src/run2.h'], ['run12.c', 'src/run1.py']),
    ('*.log\n!keep.log\n', ['run.log'], ['keep.log', 'src/keep.log']),
    ('*.log\n!keep.log\nkeep.log\n', ['keep.log', 'src/keep.log'], ['main.py']),
    ('outputs/*\n!outputs/keep.py\n', ['outputs/run.txt'], ['outputs/keep.py']),
    # Git cannot re-include a file while its parent directory is excluded.
    ('outputs/\n!outputs/keep.py\n', ['outputs/keep.py'], ['main.py']),
    ('outputs/\n!outputs/\noutputs/*\n!outputs/keep.py\n',
     ['outputs/run.txt'], ['outputs/keep.py']),
    ('# comment\n\n\\#report.txt\n\\!important.txt\n',
     ['#report.txt', '!important.txt'], ['main.py']),
    ('report.txt   \ntrailing\\ \n', ['report.txt', 'trailing '], ['trailing', 'main.py']),
    ('München/\n', ['München/result.txt'], ['src/öl.py']),
    ('cache/\n', ['src/cache/result.txt'], ['cache']),
])
def test_gitignore_patterns(tmp_path, rules, hidden, visible):
    for name in hidden + visible:
        write(tmp_path, name)
    write(tmp_path, '.looking.ignore', rules)
    ws = Workspace(tmp_path)
    assert set(ws.files()) == {'.looking.ignore', *visible}


def test_large_output_is_pruned_before_cap(tmp_path, monkeypatch):
    write(tmp_path, 'src/main.py', 'answer = 42\n')
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    for index in range(10005):
        (outputs / f'{index:05}.txt').touch()
    ws = Workspace(tmp_path)
    assert len(ws.files()) == 10000
    assert 'src/main.py' not in ws.files()
    write(tmp_path, '.looking.ignore', 'outputs/\n')
    import looking_glass.workspace as workspace
    scandir = workspace.os.scandir

    def guarded_scandir(path):
        assert Path(path) != outputs, 'Ignored directory must never be scanned'
        return scandir(path)

    monkeypatch.setattr(workspace.os, 'scandir', guarded_scandir)
    assert ws.files() == ['.looking.ignore', 'src/main.py']


def test_refresh_reloads_rules_and_preserves_open_file_and_discussion(tmp_path):
    write(tmp_path, 'outputs/report.txt', 'A unique passage.\n')
    write(tmp_path, 'src/main.py')
    app = create_app(tmp_path)
    ws = app.extensions['workspace']
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': ws.token}
    file = ws.read('outputs/report.txt')
    thread = ws.create_thread(file['path'], 0, 16, 'Keep this discussion', 'Altay', file['version'])
    initial = client.get('/fragments/files', headers=headers)
    assert 'outputs/report.txt' in initial.text
    assert client.get('/fragments/files', headers={**headers, 'If-None-Match': initial.headers['ETag']}).status_code == 304
    write(tmp_path, '.looking.ignore', 'outputs/\n')
    filtered = client.get('/fragments/files', headers={**headers, 'If-None-Match': initial.headers['ETag']})
    assert filtered.status_code == 200
    assert 'outputs/report.txt' not in filtered.text
    assert 'src/main.py' in filtered.text
    assert client.get('/api/workspace', headers=headers).json['files'] == ['.looking.ignore', 'src/main.py']
    assert ws.read(file['path']) == file
    assert ws.get_thread(thread['id'])['messages'][0]['body'] == 'Keep this discussion'
    assert Workspace(tmp_path).files() == ws.files()
    (tmp_path / '.looking.ignore').unlink()
    restored = client.get('/fragments/files', headers=headers)
    assert restored.headers['ETag'] == initial.headers['ETag']
    assert 'outputs/report.txt' in restored.text


def test_rules_file_remains_visible_and_gitignore_is_independent(tmp_path):
    write(tmp_path, 'main.py')
    write(tmp_path, '.gitignore', 'main.py\n')
    ws = Workspace(tmp_path)
    assert 'main.py' in ws.files()
    write(tmp_path, '.looking.ignore', '*\n!.gitignore\n')
    assert ws.files() == ['.gitignore', '.looking.ignore']
    write(tmp_path, '.looking.ignore', '')
    assert 'main.py' in ws.files()


def test_builtin_exclusions_and_symlinks_cannot_be_unignored(tmp_path):
    for name in EXCLUDED:
        write(tmp_path, name + '/hidden.txt')
    write(tmp_path, 'main.py')
    (tmp_path / 'alias.py').symlink_to(tmp_path / 'main.py')
    (tmp_path / 'alias-dir').symlink_to(tmp_path / '.git', target_is_directory=True)
    write(tmp_path, '.looking.ignore', '!**\n')
    assert Workspace(tmp_path).files() == ['.looking.ignore', 'main.py']


def test_symlink_rules_file_is_rejected(tmp_path):
    write(tmp_path, 'rules.txt', 'src/\n')
    (tmp_path / '.looking.ignore').symlink_to(tmp_path / 'rules.txt')
    with pytest.raises(Problem, match='must not be a symlink'):
        Workspace(tmp_path).files()


def test_workspace_switch_uses_its_own_rules(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    for root in (first, second):
        write(root, 'main.py')
        write(root, 'run.log')
    write(first, '.looking.ignore', '*.log\n')
    write(second, '.looking.ignore', '*.py\n')
    app = create_app(first)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    assert client.get('/api/workspace', headers=headers).json['files'] == ['.looking.ignore', 'main.py']
    response = client.post('/api/workspace', headers=headers, json={'path': str(second)})
    assert response.status_code == 200
    headers = {'X-Looking-Glass-Token': (second / '.looking-glass/token').read_text().strip()}
    assert client.get('/api/workspace', headers=headers).json['files'] == ['.looking.ignore', 'run.log']
