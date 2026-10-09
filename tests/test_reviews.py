import json
import pytest
from looking_glass.workspace import Workspace, Problem
from looking_glass.app import create_app
from looking_glass.reviews import accepted, splice


@pytest.fixture
def review(tmp_path):
    (tmp_path/'sample.py').write_bytes(b'first = 1\r\nsecond = 2\r\n')
    ws=Workspace(tmp_path)
    file=ws.read('sample.py')
    return ws,ws.reviews.start(file['path'],file['version'])


def edit(ws,draft,operations,role='human',author='Altay'):
    return ws.reviews.update(draft['id'],draft['version'],operations,author,role)


def test_provenance_persistence_and_exact_approval(review):
    ws,draft=review; original=(ws.root/'sample.py').read_bytes()
    (ws.root/'sample.py').chmod(0o640)
    draft=edit(ws,draft,[dict(start=8,end=9,insert='9')])
    draft=edit(ws,draft,[dict(start=len(draft['content']),end=len(draft['content']),insert='third = "🧠"\r\n')],'agent','Codex')
    assert (ws.root/'sample.py').read_bytes()==original
    assert accepted(draft['segments'])==draft['content']
    assert any(s['kind']=='delete' and s['text']=='1' for s in draft['segments'])
    assert any(s.get('role')=='agent' and s['kind']=='insert' for s in draft['segments'])
    restarted=Workspace(ws.root)
    assert restarted.reviews.read(draft['id'])==draft
    history=restarted.reviews.history(draft['id'],limit=1)
    assert history['edits'][0]['operations'][0]['removed']=='1'
    assert history['edits'][0]['created_at'].endswith('Z')
    assert restarted.reviews.history(draft['id'],history['next_after'])['edits'][0]['role']=='agent'
    saved=ws.reviews.approve(draft['id'],draft['version'])
    assert (ws.root/'sample.py').read_bytes()==draft['content'].encode()
    assert (ws.root/'sample.py').stat().st_mode & 0o777==0o640
    assert saved['content']==draft['content']
    assert ws.reviews.list()==[]
    new=ws.reviews.start(saved['path'],saved['version'])
    assert new['id']!=draft['id'] and new['segments']==[dict(kind='base',text=saved['content'])]


def test_stale_edits_and_external_original_never_overwrite(review):
    ws,draft=review
    changed=edit(ws,draft,[dict(start=0,end=0,insert='# hi\r\n')])
    with pytest.raises(Problem) as error: edit(ws,draft,[dict(start=0,end=1,insert='x')])
    assert error.value.status==409
    (ws.root/'sample.py').write_text('external content')
    with pytest.raises(Problem) as error: ws.reviews.approve(changed['id'],changed['version'])
    assert error.value.status==409
    assert ws.reviews.read(draft['id'])==changed
    assert (ws.root/'sample.py').read_text()=='external content'


def test_draft_threads_are_separate_and_promoted(review):
    ws,draft=review
    original=ws.create_thread('sample.py',0,5,'old','Altay',draft['base_version'])
    # Starting a review before an existing comment also gets an anchor lazily.
    draft=edit(ws,draft,[dict(start=0,end=0,insert='new ')] )
    thread=ws.reviews.create_thread(draft['id'],draft['version'],0,3,'draft','Altay')
    assert thread['quote']=='new'
    assert len(ws.threads('sample.py'))==1
    assert ws.thread_context(thread['id'])['context']['content'].startswith('new ')
    ws.reply(thread['id'],'reply','Agent')
    assert ws.get_thread(thread['id'])['messages'][-1]['origin']['snapshot_hash']!=draft['base_version']
    draft=edit(ws,draft,[dict(start=0,end=0,insert='x ')] )
    assert ws.get_thread(thread['id'])['start']==2
    ws.read('sample.py')
    assert ws.get_thread(thread['id'])['quote']=='new'
    ws.reviews.approve(draft['id'],draft['version'])
    assert len(ws.threads('sample.py'))==2
    assert ws.get_thread(thread['id'])['start']==2
    assert ws.get_thread(original['id'])['quote']=='first'


def test_existing_anchor_isolated(review):
    ws,unused=review
    # Fresh file review copies existing discussion anchors.
    saved=ws.read('sample.py')
    existing=ws.create_thread('sample.py',0,5,'comment','Altay',saved['version'])
    (ws.root/'other.py').write_text('first = 1\n')
    file=ws.read('other.py'); t=ws.create_thread('other.py',0,5,'comment','Altay',file['version'])
    draft=ws.reviews.start('other.py',file['version'])
    draft=edit(ws,draft,[dict(start=0,end=0,insert='#\n')])
    assert ws.get_thread(t['id'],review=draft['id'])['start']==2
    assert ws.get_thread(t['id'])['start']==0
    ws.reviews.approve(draft['id'],draft['version'])
    assert ws.get_thread(t['id'])['start']==2
    assert ws.get_thread(existing['id'])['start']==0


@pytest.mark.parametrize('ops',[
    [dict(start=True,end=0,insert='x')], [dict(start=-1,end=0,insert='x')],
    [dict(start=0,end=10000,insert='x')], [dict(start=0,end=0,insert='\x00')],
    [dict(start=0,end=0,insert=2)], [dict(start=0,end=0,insert='x',extra=2)], [],
])
def test_invalid_edits_atomic(review,ops):
    ws,draft=review
    with pytest.raises(Problem): edit(ws,draft,ops)
    assert ws.reviews.read(draft['id'])==draft
    assert ws.reviews.history(draft['id'])['edits']==[]


def test_undo_restores_base_and_deleted_insertions_only_keep_history(review):
    ws,draft=review
    draft=edit(ws,draft,[dict(start=0,end=5,insert='')])
    draft=edit(ws,draft,[dict(start=0,end=0,insert='first')])
    assert draft['segments']==[dict(kind='base',text=draft['base'])]
    draft=edit(ws,draft,[dict(start=0,end=0,insert='temporary')])
    draft=edit(ws,draft,[dict(start=0,end=9,insert='')])
    assert draft['segments']==[dict(kind='base',text=draft['base'])]
    assert len(ws.reviews.history(draft['id'])['edits'])==4


def test_api_auth_revision_poll_and_agent_contract(review):
    ws,_=review; app=create_app(ws.root); c=app.test_client();h={'X-Looking-Glass-Token':ws.token}
    assert c.get('/api/reviews').status_code==401
    drafts=c.get('/api/reviews',headers=h).json['reviews']; identifier=drafts[0]['id']
    draft=c.get(f'/api/reviews/{identifier}',headers=h).json
    assert c.get(f'/api/reviews/{identifier}?version='+draft['version'],headers=h).status_code==304
    result=c.patch(f'/api/reviews/{identifier}',headers=h,json=dict(version=draft['version'],operations=[dict(start=0,end=0,insert='🧠 ')],author='Codex',role='agent'))
    assert result.status_code==200 and result.json['content'].startswith('🧠 ')
    thread=c.post('/api/threads',headers=h,json=dict(path='sample.py',review_id=identifier,version=result.json['version'],start=0,end=1,author='Altay',body='brain')).json
    assert c.get('/api/threads?path=sample.py',headers=h).json==[]
    assert c.get(f'/api/threads?path=sample.py&review={identifier}',headers=h).json[0]['id']==thread['id']
    assert c.get(f'/api/reviews/{identifier}/edits',headers=h).json['edits'][0]['author']=='Codex'
    assert c.post(f'/api/reviews/{identifier}/approve',headers=h,json={'version':draft['version']}).status_code==409
    assert c.post(f'/api/reviews/{identifier}/approve',headers=h,json={'version':result.json['version']}).status_code==200
