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
    assert client.get('/api/tasks/1/activity').status_code == 401
    assert client.post('/api/tasks',headers=headers,json={'action':'comment','id':1,'body':'API comment','author':'Agent'}).status_code == 200
    activity=client.get('/api/tasks/1/activity',headers=headers).json
    assert activity['entries'][-1]['body']=='API comment'
    assert client.get('/api/tasks/1/activity?revision=2',headers=headers).status_code == 304
    assert client.get('/api/tasks/1/activity?limit=0',headers=headers).status_code == 400
    assert client.get('/api/tasks/99/activity',headers=headers).status_code == 404


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


def test_card_activity_is_atomic_and_tracks_implicit_changes(tmp_path):
    tasks = Workspace(tmp_path).tasks
    def change(**data):
        return tasks.mutate(dict(revision=tasks.read()['revision'], author='Pat', **data))
    change(action='create', title='Epic')
    change(action='create', title='Task')
    change(action='update', ids=[1], changes={'milestone':True})
    change(action='update', ids=[2], changes={'milestone_id':1,'title':'New title','description':'Details'})
    latest = tasks.activity(2)['entries'][-1]
    assert latest['author'] == 'Pat'
    assert latest['changes']['title'] == {'from':'Task','to':'New title'}
    assert latest['changes']['milestone_id'] == {'from':None,'to':1}
    before = tasks.activity(2)
    with pytest.raises(Problem):
        tasks.mutate(dict(action='update',revision=0,ids=[2],changes={'title':'Overwrite'}))
    assert tasks.activity(2) == before
    change(action='update',ids=[2],changes={'title':'New title','status':'backlog'})
    assert tasks.activity(2)['entries'] == before['entries']  # no-op save
    change(action='delete',ids=[1])
    assert tasks.activity(2)['entries'][-1]['changes']['milestone_id'] == {'from':1,'to':None}
    change(action='move',id=2,status='done')
    assert tasks.activity(2)['entries'][-1]['changes']['status'] == {'from':'backlog','to':'done'}


def test_comments_deletion_pagination_and_stable_references(tmp_path):
    tasks = Workspace(tmp_path).tasks
    tasks.mutate(dict(action='create',title='Plan',revision=0))
    # Appending messages does not require the board revision and preserves card edits.
    tasks.mutate(dict(action='comment',id=1,body='<script>literal</script>\nReply',author='Agent'))
    tasks.mutate(dict(action='comment',id=1,body='Second',author='Human',revision=0))
    page = tasks.activity(1,limit=2)
    assert page['has_older']
    assert [entry['kind'] for entry in page['entries']] == ['comment','comment']
    assert tasks.activity(1,known_revision=page['revision']) is None
    assert tasks.activity(1,limit=2,before=page['entries'][0]['id'])['entries'][0]['body'] == 'Created card.'
    entry_id=page['entries'][-1]['id']
    tasks.mutate(dict(action='delete_activity',id=1,entry_id=entry_id))
    assert entry_id not in [entry['id'] for entry in tasks.activity(1)['entries']]
    tasks.mutate(dict(action='delete',ids=[1],revision=tasks.read()['revision']))
    with pytest.raises(Problem): tasks.activity(1)
    tasks = Workspace(tmp_path).tasks
    result = tasks.mutate(dict(action='create',title='Next',revision=tasks.read()['revision']))
    assert result['cards'][0]['id'] == 2
    assert result['cards'][0]['reference'] == '#C02'
    assert tasks.activity(2)['entries'][0]['id'] > entry_id


def test_activity_scoped_validation_and_snapshots(tmp_path):
    import io
    from looking_glass import database
    tasks=Workspace(tmp_path).tasks
    for title in ('A','B'):
        tasks.mutate(dict(action='create',title=title,revision=tasks.read()['revision']))
    tasks.mutate(dict(action='comment',id=1,body='Retained café 🪞'))
    entry=tasks.activity(1)['entries'][-1]
    for data in (dict(action='delete_activity',id=2,entry_id=entry['id']),dict(action='comment',id=1,body=' '),dict(action='comment',id=True,body='Invalid'),dict(action='comment',id=1,body='x',author=123)):
        before=tasks.read()
        with pytest.raises(Problem): tasks.mutate(data)
        assert tasks.read()==before
    output=io.StringIO();database.dump(tmp_path,output)
    target=tmp_path/'restored';target.mkdir()
    database.restore(target,output.getvalue())
    assert Workspace(target).tasks.activity(1)==tasks.activity(1)


def test_cli_card_conversation_and_prefixed_ids(tmp_path,monkeypatch,capsys):
    import json
    import looking_glass.cli as cli
    tasks=Workspace(tmp_path).tasks
    monkeypatch.setattr(cli,'project_root',lambda _:tmp_path)
    monkeypatch.setattr(cli,'project_url',lambda *_:'http://127.0.0.1:8765')
    monkeypatch.setattr(cli,'check_project',lambda *_:None)
    def api(root,url,route,method='GET',data=None):
        if route.startswith('tasks/1/activity'):
            return tasks.activity(1)
        return tasks.read() if method=='GET' else tasks.mutate(data)
    monkeypatch.setattr(cli,'api',api)
    cli.main(['tasks','create','Plan'])
    capsys.readouterr()
    body=tmp_path/'comment.txt';body.write_text('CLI reply\nUnicode café')
    cli.main(['tasks','comment','#C01','--body-file',str(body),'--author','Agent A'])
    capsys.readouterr()
    cli.main(['tasks','activity','C01'])
    entries=json.loads(capsys.readouterr().out)['entries']
    assert entries[-1]['body']=='CLI reply\nUnicode café'
    assert entries[-1]['author']=='Agent A'
    cli.main(['tasks','delete-activity','C01',str(entries[-1]['id'])])
    assert len(tasks.activity(1)['entries'])==1


def test_upgrade_retains_existing_cards_and_starts_history_without_inventing_it(tmp_path):
    ws=Workspace(tmp_path)
    with ws.connection() as db:
        db.execute('DROP TABLE task_activity')
        db.execute('DROP TABLE task_board_revision')
        db.execute('CREATE TABLE task_board_revision(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL)')
        db.execute('INSERT INTO task_board_revision VALUES(1,7)')
        db.execute("INSERT INTO tasks(id,title) VALUES(12,'Existing')")
    tasks=Workspace(tmp_path).tasks
    assert tasks.read()['revision']==7
    assert tasks.read()['cards'][0]['reference']=='#C12'
    assert tasks.activity(12)['entries']==[]
    result=tasks.mutate(dict(action='create',title='New',revision=7))
    assert result['cards'][0]['id']==12
    assert result['cards'][1]['reference']=='#C13'
