import io

import pytest

from looking_glass import database
from looking_glass.workspace import Workspace, Problem


def planner(tmp_path):
    tasks = Workspace(tmp_path).tasks
    def change(**data):
        return tasks.mutate(dict(revision=tasks.read()['revision'], author='Agent', **data))
    def cards():
        return {c['id']: c for c in tasks.read()['cards']}
    return tasks, change, cards


def test_nested_checklists_inherit_milestones_and_subtrees_travel_atomically(tmp_path):
    tasks, change, cards = planner(tmp_path)
    for title in ('First', 'Second', 'Parent'):
        change(action='create', title=title)
    change(action='update', ids=[1,2], changes={'milestone': True})
    change(action='create', title='Child', parent_id=3)
    change(action='create', title='Grandchild', parent_id=4)
    change(action='outline_move', ids=[3], parent_id=1)
    assert [cards()[i]['milestone_id'] for i in (3,4,5)] == [1,1,1]
    assert cards()[5]['parent_id'] == 4
    change(action='outline_move', ids=[3,4], parent_id=2)
    assert [cards()[i]['milestone_id'] for i in (3,4,5)] == [2,2,2]
    assert cards()[4]['parent_id'] == 3  # selected descendant travels once
    assert tasks.activity(5)['entries'][-1]['changes']['milestone_id'] == {'from':1,'to':2}
    change(action='update', ids=[3], changes={'milestone_id': None})
    assert all(cards()[i]['milestone_id'] is None for i in (3,4,5))
    assert cards()[4]['parent_id'] == 3
    assert Workspace(tmp_path).tasks.read() == tasks.read()
    output = io.StringIO(); database.dump(tmp_path, output)
    destination = tmp_path/'restored'; destination.mkdir()
    database.restore(destination, output.getvalue())
    assert Workspace(destination).tasks.read() == tasks.read()


def test_hierarchy_rejects_cycles_invalid_moves_and_stale_edits_without_partial_writes(tmp_path):
    tasks, change, cards = planner(tmp_path)
    for title in ('Milestone','Parent','Child','Other'):
        change(action='create', title=title)
    change(action='update',ids=[1],changes={'milestone':True})
    change(action='outline_move',ids=[2],parent_id=1)
    change(action='outline_move',ids=[3],parent_id=2)
    for data in (
        dict(action='outline_move',ids=[2],parent_id=3),
        dict(action='outline_move',ids=[1],parent_id=4),
        dict(action='outline_move',ids=[2],parent_id=2),
        dict(action='outline_move',ids=[3],parent_id=1,before=4),
        dict(action='outline_move',ids=[3],parent_id=True),
        dict(action='outline_move',ids=[2,2],parent_id=None),
        dict(action='outline_move',ids=[99],parent_id=1),
        dict(action='update',ids=[2],changes={'parent_id':3}),
        dict(action='update',ids=[2],changes={'parent_id':1,'milestone_id':1}),
        dict(action='create',title='Invalid',parent_id=999),
    ):
        before=tasks.read(); history=tasks.activity(2)
        with pytest.raises(Problem): change(**data)
        assert tasks.read()==before
        assert tasks.activity(2)==history
    with pytest.raises(Problem):
        tasks.mutate(dict(action='outline_move',ids=[3],parent_id=4,revision=0))
    change(action='update',ids=[4],changes={'archived':True})
    with pytest.raises(Problem): change(action='outline_move',ids=[3],parent_id=4)
    with pytest.raises(Problem): change(action='outline_move',ids=[4],parent_id=None)


def test_outline_order_is_separate_from_column_order_and_records_actual_reorders(tmp_path):
    tasks, change, cards = planner(tmp_path)
    for title in ('A','B','C','D'): change(action='create',title=title)
    initial = [c['id'] for c in tasks.read()['cards']]
    change(action='outline_move',ids=[4,3],parent_id=None,before=1)
    assert [c['id'] for c in tasks.read()['cards']] == initial
    assert [c['id'] for c in sorted(cards().values(),key=lambda c:c['outline_position'])] == [4,3,1,2]
    assert tasks.activity(4)['entries'][-1]['changes']['outline_position'] == {'from':4,'to':1}
    history=tasks.activity(4)['entries']
    change(action='outline_move',ids=[4],parent_id=None,before=3)
    assert tasks.activity(4)['entries']==history
    positions={i:c['outline_position'] for i,c in cards().items()}
    change(action='move',id=2,status='done')
    assert {i:c['outline_position'] for i,c in cards().items()}==positions


def test_deleting_and_promoting_parents_preserves_nested_cards(tmp_path):
    tasks, change, cards = planner(tmp_path)
    change(action='create',title='Epic')
    change(action='update',ids=[1],changes={'milestone':True})
    for parent in (1,2,3): change(action='create',title='Subitem',parent_id=parent)
    change(action='delete',ids=[2,3])
    assert cards()[4]['parent_id']==1 and cards()[4]['milestone_id']==1
    change(action='create',title='Leaf',parent_id=4)
    change(action='update',ids=[4],changes={'milestone':True})
    assert cards()[4]['parent_id'] is None and cards()[5]['milestone_id']==4
    change(action='update',ids=[4],changes={'milestone':False})
    assert cards()[5]['parent_id'] is None and cards()[5]['milestone_id'] is None
    change(action='delete',ids=[1])
    assert len(cards())==2


def test_old_board_migrates_assignment_and_order_without_changing_card_ids(tmp_path):
    tasks, change, cards = planner(tmp_path)
    for title in ('Epic','Child','Other'): change(action='create',title=title)
    change(action='update',ids=[1],changes={'milestone':True})
    change(action='update',ids=[2],changes={'milestone_id':1})
    change(action='move',id=3,status='backlog',before=2)
    before=tasks.read()
    with tasks.ws.connection() as db:
        db.execute('ALTER TABLE tasks DROP COLUMN parent_id')
        db.execute('ALTER TABLE tasks DROP COLUMN outline_position')
    migrated=Workspace(tmp_path).tasks.read()
    assert migrated['revision']==before['revision']
    for card in migrated['cards']:
        assert card['parent_id']==card['milestone_id']
        assert card['outline_position']==card['position']
    assert next(c for c in migrated['cards'] if c['id']==1)['reference']=='#M1'


def test_cli_creates_moves_and_reads_card_subtrees(tmp_path, monkeypatch, capsys):
    import json
    import looking_glass.cli as cli
    tasks, change, cards = planner(tmp_path)
    monkeypatch.setattr(cli,'project_root',lambda _:tmp_path)
    monkeypatch.setattr(cli,'project_url',lambda *_:'http://127.0.0.1:8765')
    monkeypatch.setattr(cli,'check_project',lambda *_:None)
    monkeypatch.setattr(cli,'api',lambda root,url,route,method='GET',data=None:tasks.read() if method=='GET' else tasks.mutate(data))
    cli.main(['tasks','create','Parent'])
    cli.main(['tasks','create','Child','--parent-id','C01'])
    cli.main(['tasks','create','Leaf','--parent-id','C02'])
    cli.main(['tasks','create','Other'])
    capsys.readouterr()
    cli.main(['tasks','read','C02'])
    assert [c['id'] for c in json.loads(capsys.readouterr().out)['cards']]==[2,3]
    cli.main(['tasks','outline-move','C02','--parent-id','C04','--revision',str(tasks.read()['revision'])])
    assert cards()[2]['parent_id']==4 and cards()[3]['parent_id']==2
    cli.main(['tasks','update','C02','--parent-id','0','--revision',str(tasks.read()['revision'])])
    assert cards()[2]['parent_id'] is None


def test_depth_bound_and_noop_demotion_preserve_existing_checklists(tmp_path):
    tasks, change, cards = planner(tmp_path)
    for identifier in range(1,33):
        change(action='create',title=f'Level {identifier}',parent_id=identifier-1 or None)
    before=tasks.read()
    with pytest.raises(Problem,match='32 levels'):
        change(action='create',title='Too deep',parent_id=32)
    assert tasks.read()==before
    change(action='update',ids=[2],changes={'milestone':False})
    assert cards()[3]['parent_id']==2
