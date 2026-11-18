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
    cli.main(['tasks','list','--query','M01'])
    milestone=json.loads(capsys.readouterr().out)['cards'][0]
    assert milestone['reference']=='#M1' and milestone['card_reference']=='#C01'
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


def test_activity_paginates_by_exclusive_id_and_validates_large_identifiers(tmp_path):
    tasks = Workspace(tmp_path).tasks
    tasks.mutate(dict(action='create', title='Plan', revision=0))
    tasks.mutate(dict(action='create', title='Other', revision=1))
    for identifier in (1, 2, 1, 2, 1):
        tasks.mutate(dict(action='comment', id=identifier, body='Progress'))
    newest = tasks.activity(1, limit=2)
    assert [entry['id'] for entry in newest['entries']] == [5, 7]
    assert newest['has_older']
    earlier = tasks.activity(1, before=5, limit=2)
    assert [entry['id'] for entry in earlier['entries']] == [1, 3]
    assert not earlier['has_older']
    assert tasks.activity(1, before=2**63, limit=2) == newest
    with pytest.raises(Problem):
        tasks.activity(2**63)
    with pytest.raises(Problem):
        tasks.mutate(dict(action='delete_activity', id=1, entry_id=2**63))
    with pytest.raises(Problem):
        tasks.mutate(dict(action='create', title='Invalid parent', parent_id=2**63, revision=7))


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


def test_saved_milestone_numbers_preserve_permanent_ids(tmp_path):
    tasks=Workspace(tmp_path).tasks
    def change(**data):
        return tasks.mutate(dict(revision=tasks.read()['revision'],**data))
    def cards():
        return {c['id']:c for c in tasks.read()['cards']}
    for title in ('Task','First','Second'):
        change(action='create',title=title)
    change(action='update',ids=[3],changes={'milestone':True})
    assert cards()[3]['reference']=='#M1'
    change(action='update',ids=[2],changes={'milestone':True})
    assert cards()[2]['reference']=='#M2' and cards()[3]['reference']=='#M1'
    assert cards()[2]['card_reference']=='#C02' and cards()[3]['card_reference']=='#C03'
    change(action='move',id=3,status='done')
    change(action='update',ids=[2],changes={'archived':True})
    assert cards()[2]['reference']=='#M2' and cards()[3]['reference']=='#M1'
    change(action='delete',ids=[2])
    assert cards()[3]['reference']=='#M1'
    change(action='update',ids=[3],changes={'milestone':False})
    assert cards()[3]['reference']=='#C03' and cards()[3]['milestone_reference'] is None
    change(action='update',ids=[3],changes={'milestone':True})
    restarted=Workspace(tmp_path).tasks.read()
    milestone=next(c for c in restarted['cards'] if c['id']==3)
    assert milestone['reference']=='#M1' and milestone['card_reference']=='#C03'
    assert cards()[1]['reference']=='#C01'


def test_milestone_renumbering_does_not_rewrite_activity_or_assignments(tmp_path):
    tasks=Workspace(tmp_path).tasks
    def change(**data):
        return tasks.mutate(dict(revision=tasks.read()['revision'],**data))
    for title in ('First','Second','Child'):
        change(action='create',title=title)
    change(action='update',ids=[1,2],changes={'milestone':True})
    change(action='update',ids=[3],changes={'milestone_id':2})
    history=tasks.activity(3)['entries']
    before=tasks.read()
    with pytest.raises(Problem):
        tasks.mutate(dict(action='update',ids=[1],changes={'milestone':False},revision=0))
    assert tasks.read()==before
    change(action='milestone_move',id=2,before=1)
    assert next(c for c in tasks.read()['cards'] if c['id']==2)['reference']=='#M1'
    assert next(c for c in tasks.read()['cards'] if c['id']==3)['milestone_id']==2
    assert tasks.activity(3)['entries']==history
    assert history[-1]['changes']['milestone_id']['to']==2


def test_milestone_reordering_reuses_active_numbers_and_rejects_invalid_moves(tmp_path):
    tasks=Workspace(tmp_path).tasks
    def change(**data):
        return tasks.mutate(dict(revision=tasks.read()['revision'], author='Planner', **data))
    for title in ('First', 'Archived', 'Third', 'Fourth', 'Task'):
        change(action='create', title=title)
    change(action='update', ids=[1, 2, 3, 4], changes={'milestone': True})
    change(action='update', ids=[2], changes={'archived': True})
    before=tasks.read()
    for source, target in ((2, 1), (5, 1), (1, 1), (1, 2), (1, 5), (1, True), (1, 999)):
        with pytest.raises(Problem):
            change(action='milestone_move', id=source, before=target)
        assert tasks.read() == before
    with pytest.raises(Problem):
        change(action='update', ids=[1], changes={'milestone_number': 12})
    with pytest.raises(Problem) as error:
        tasks.mutate(dict(action='milestone_move', revision=0, id=4, before=1))
    assert error.value.status == 409
    assert tasks.read() == before

    result = change(action='milestone_move', id=4, before=1)
    assert [card['reference'] for card in result['cards']] == ['#M3', '#M2', '#M4', '#M1', '#C05']
    assert tasks.activity(4)['entries'][-1]['changes']['milestone_number'] == {'from': 4, 'to': 1}
    assert tasks.activity(1)['entries'][-1]['changes']['milestone_number'] == {'from': 1, 'to': 3}
    assert change(action='milestone_move', id=4, before=1) == result
    assert Workspace(tmp_path).tasks.read() == result


def test_number_migration_and_database_snapshot_preserve_plan(tmp_path):
    import io
    from looking_glass import database
    ws=Workspace(tmp_path)
    with ws.connection() as db:
        db.execute('DROP INDEX task_milestone_numbers')
        db.execute('ALTER TABLE tasks DROP COLUMN milestone_number')
        db.execute("INSERT INTO tasks(id,title,milestone) VALUES(4,'Earlier milestone',1),(9,'Later milestone',1)")
    tasks=Workspace(tmp_path).tasks
    assert [c['reference'] for c in tasks.read()['cards']]==['#M1','#M2']
    with ws.connection() as db:
        db.execute('UPDATE tasks SET milestone_number=42 WHERE id=9')
    tasks.mutate(dict(action='milestone_move',revision=0,id=9,before=4))
    assert [c['reference'] for c in Workspace(tmp_path).tasks.read()['cards']]==['#M42','#M1']
    output=io.StringIO();database.dump(tmp_path,output)
    restored=tmp_path/'restored';restored.mkdir();database.restore(restored,output.getvalue())
    assert Workspace(restored).tasks.read()==tasks.read()
    result=tasks.mutate(dict(action='update',revision=1,ids=[9],changes={'milestone':False}))
    assert next(c for c in result['cards'] if c['id']==4)['reference']=='#M42'


def test_done_column_archive_is_atomic_and_preserves_outline_assignments(tmp_path):
    tasks = Workspace(tmp_path).tasks

    def change(**data):
        return tasks.mutate({'revision': tasks.read()['revision'], **data})

    change(action='create', title='Milestone', milestone=True, status='done')
    change(action='create', title='Done parent', parent_id=1, status='done')
    change(action='create', title='Active child', parent_id=2, status='in_progress')
    change(action='create', title='Other done task', status='done')
    before = tasks.read()
    for ids in ([2, 1], [2, 3], [2, 2], [2, 99], [True]):
        with pytest.raises(Problem):
            change(action='archive_done', ids=ids)
        assert tasks.read() == before
    after = change(action='archive_done', ids=[2])
    parent, child, other = after['cards'][1:]
    assert (parent['archived'], child['archived'], other['archived']) == (1, 0, 0)
    assert (parent['status'], child['parent_id'], child['milestone_id']) == ('done', 2, 1)
    assert tasks.activity(2)['entries'][-1]['changes']['archived'] == {'from': 0, 'to': 1}


def test_milestone_creation_inserts_at_the_requested_position(tmp_path):
    tasks = Workspace(tmp_path).tasks

    def change(**data):
        return tasks.mutate({'revision': tasks.read()['revision'], **data})

    change(action='create', title='First', milestone=True)
    change(action='create', title='Reserved', milestone=True)
    change(action='update', ids=[2], changes={'archived': True})
    change(action='create', title='Later', milestone=True)
    change(action='create', title='Task under Later', parent_id=3)
    before = tasks.read()
    for placement in ({'before': 2}, {'before': 4}, {'parent_id': 3}):
        with pytest.raises(Problem):
            change(action='create', title='Invalid', milestone=True, **placement)
        assert tasks.read() == before
    result = change(action='create', title='Inserted', milestone=True, before=3)
    assert [card['reference'] for card in result['cards']] == ['#M1', '#M2', '#M4', '#C04', '#M3']
    assert result['cards'][3]['milestone_id'] == 3
    assert tasks.activity(3)['entries'][-1]['changes']['milestone_number'] == {'from': 3, 'to': 4}
    assert tasks.activity(5)['entries'][-1]['changes']['milestone_number'] == {'from': None, 'to': 3}
