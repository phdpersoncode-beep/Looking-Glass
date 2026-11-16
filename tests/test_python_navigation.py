import subprocess

import pytest

from looking_glass.app import create_app
from looking_glass.python_navigation import definitions
from looking_glass.workspace import Problem, Workspace


def lookup(root, content, line, column, path='main.py'):
    (root/path).write_text(content)
    return definitions(Workspace(root), dict(path=path,content=content,line=line,column=column))['definitions']


def test_definitions_resolve_imports_aliases_methods_and_relative_packages(tmp_path):
    (tmp_path/'helper.py').write_text('def build(value):\n    return value\n')
    source = 'from helper import build as make\nanswer = make(2)\n'
    target = lookup(tmp_path, source, 2, 11)[0]
    assert (target['path'], target['line'], target['column'], target['name']) == ('helper.py',1,4,'build')
    source = 'class Part:\n    def build(self):\n        pass\np = Part()\np.build()\n'
    target = lookup(tmp_path, source, 5, 4)[0]
    assert target['line'] == 2 and target['column'] == 8
    (tmp_path/'pkg').mkdir(); (tmp_path/'pkg/__init__.py').write_text('')
    (tmp_path/'pkg/helper.py').write_text('class Result: pass\n')
    target = lookup(tmp_path, 'from .helper import Result\nResult()\n',2,3,'pkg/main.py')[0]
    assert target['path'] == 'pkg/helper.py' and target['name'] == 'Result'


def test_current_unsaved_source_unicode_crlf_and_scopes(tmp_path):
    (tmp_path/'main.py').write_text('disk = 1\n')
    source = 'def café():\r\n    return 2\r\nvalue = "🦊"; café()\r\n'
    target = definitions(Workspace(tmp_path), dict(path='main.py',content=source,line=3,column=15))['definitions'][0]
    assert target['line'] == 1 and target['column'] == 4
    assert (tmp_path/'main.py').read_text() == 'disk = 1\n'
    source = 'value = 1\ndef work():\n    value = 2\n    return value\n'
    assert lookup(tmp_path, source, 4, 13)[0]['line'] == 3
    assert lookup(tmp_path, 'def run():\n    pass\nrun(\n', 3, 2)[0]['line'] == 1


def test_navigation_never_executes_project_code_and_rejects_hidden_targets(tmp_path):
    sentinel = tmp_path/'EXECUTED'
    (tmp_path/'helper.py').write_text(f'from pathlib import Path\nPath({str(sentinel)!r}).touch()\ndef safe(): pass\n')
    (tmp_path/'sitecustomize.py').write_text(f'open({str(sentinel)!r}, "w").close()\n')
    assert lookup(tmp_path, 'from helper import safe\nsafe()\n', 2, 2)[0]['path'] == 'helper.py'
    assert not sentinel.exists()
    assert lookup(tmp_path, 'import os\nos.path.join("a", "b")\n', 2, 10) == []
    (tmp_path/'.venv').mkdir(); (tmp_path/'.venv/hidden.py').write_text('def hidden(): pass\n')
    assert lookup(tmp_path, 'missing_name()\n', 1, 3) == []


def test_api_validates_authentication_paths_and_bounded_work(tmp_path, monkeypatch):
    (tmp_path/'main.py').write_text('x = 1\nx\n')
    app = create_app(tmp_path); client = app.test_client(); ws = app.extensions['workspace']
    headers = {'X-Looking-Glass-Token':ws.token}
    data = dict(path='main.py',content='x = 1\nx\n',line=2,column=0)
    assert client.post('/api/python/definition', json=data).status_code == 401
    assert client.post('/api/python/definition', headers=headers, json=data).json['definitions'][0]['line'] == 1
    for changes, status in [({'line':True},400), ({'column':-1},400), ({'line':99},400),
                            ({'content':'x'*524289},413), ({'path':'../bad.py'},403)]:
        assert client.post('/api/python/definition', headers=headers, json={**data,**changes}).status_code == status
    import looking_glass.python_navigation as navigation
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('python', 4)
    with monkeypatch.context() as patch:
        patch.setattr(navigation.subprocess, 'run', timeout)
        assert client.post('/api/python/definition', headers=headers, json=data).status_code == 408
    assert navigation._worker.acquire(blocking=False)
    try:
        assert client.post('/api/python/definition', headers=headers, json=data).status_code == 429
    finally:
        navigation._worker.release()
    assert client.post('/api/python/definition', headers=headers, json=data).status_code == 200
