import pytest
from looking_glass.app import create_app
from looking_glass.workspace import Workspace, Problem


def test_tasks_persistence_hierarchy_and_atomic_conflicts(tmp_path):
    ws = Workspace(tmp_path)
    def change(**data):
        return ws.tasks.mutate(dict(revision=ws.tasks.read()['revision'], **data))
    change(action='create', title='Release')
    change(action='create', title='Build')
    change(action='update', ids=[1], changes={'milestone': True})
    change(action='update', ids=[2], changes={'milestone_id': 1})
    assert Workspace(tmp_path).tasks.read()['cards'][1]['milestone_id'] == 1
    with pytest.raises(Problem):
        change(action='update', ids=[1], changes={'milestone_id': 1})
    with pytest.raises(Problem):
        ws.tasks.mutate(dict(action='delete', ids=[2], revision=0))
    assert len(ws.tasks.read()['cards']) == 2
    change(action='delete', ids=[1])
    assert ws.tasks.read()['cards'][0]['milestone_id'] is None


def test_order_bulk_archive_and_validation(tmp_path):
    tasks = Workspace(tmp_path).tasks
    def change(**data):
        return tasks.mutate(dict(revision=tasks.read()['revision'], **data))
    for title in ('A', 'B', 'C'):
        change(action='create', title=title)
    result = change(action='move', id=3, status='backlog', before=1)
    assert [c['id'] for c in result['cards']] == [3, 1, 2]
    result = change(action='update', ids=[1, 2], changes={'archived': True, 'status': 'done'})
    assert all(c['archived'] and c['status'] == 'done' for c in result['cards'] if c['id'] in (1, 2))
    for data in [dict(action='create', title=' '), dict(action='update', ids=[1], changes={'status':'bogus'}), dict(action='update', ids=[1, 99], changes={'title':'Oops'}),dict(action='update', ids=[1], changes={'milestone_id':True})]:
        before = tasks.read()
        with pytest.raises(Problem):
            change(**data)
        assert tasks.read() == before


def test_api_security_and_workspace_switch(tmp_path):
    app = create_app(tmp_path)
    client = app.test_client()
    assert client.get('/api/tasks').status_code == 401
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    assert client.post('/api/tasks', headers=headers, json={'action':'create','title':'Plan','revision':0}).status_code == 200
    assert client.post('/api/tasks', headers=headers, json={'action':'delete','ids':[1],'revision':0}).status_code == 409
    assert client.get('/api/tasks', headers=headers).json['cards'][0]['title'] == 'Plan'
    assert client.get('/api/tasks?revision=1', headers=headers).status_code == 304
    assert client.get('/api/tasks?revision=0', headers=headers).status_code == 200


def test_cli_shared_tasks(tmp_path, monkeypatch, capsys):
    import looking_glass.cli as cli
    tasks = Workspace(tmp_path).tasks
    monkeypatch.setattr(cli, 'project_root', lambda _: tmp_path)
    monkeypatch.setattr(cli, 'project_url', lambda *_: 'http://127.0.0.1:8765')
    monkeypatch.setattr(cli, 'check_project', lambda *_: None)
    monkeypatch.setattr(cli, 'api', lambda root,url,route,method='GET',data=None: tasks.read() if method == 'GET' else tasks.mutate(data))
    cli.main(['tasks','create','Release'])
    cli.main(['tasks','update','1','--revision','1','--milestone'])
    cli.main(['tasks','read','1'])
    assert 'Release' in capsys.readouterr().out
    assert tasks.read()['cards'][0]['milestone']
    cli.main(['tasks','list','--query','rls','--milestone-id','1','--status','backlog'])
    import json
    assert json.loads(capsys.readouterr().out)['cards'][0]['title'] == 'Release'
    cli.main(['tasks','list','--query','missing'])
    assert json.loads(capsys.readouterr().out)['cards'] == []


def test_board_survives_database_snapshot(tmp_path):
    import io
    from looking_glass import database
    source = tmp_path/'source'
    source.mkdir()
    tasks = Workspace(source).tasks
    tasks.mutate(dict(action='create', revision=0, title='Keep me'))
    tasks.mutate(dict(action='update', revision=1, ids=[1], changes={'milestone':True,'description':'Unicode café 🪞'}))
    output = io.StringIO()
    database.dump(source, output)
    target = tmp_path/'target'
    target.mkdir()
    database.restore(target, output.getvalue())
    assert Workspace(target).tasks.read() == tasks.read()
