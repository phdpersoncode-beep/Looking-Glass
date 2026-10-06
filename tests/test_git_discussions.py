import io
import json
import pytest
from test_history import history_repo, git
from looking_glass.app import create_app
from looking_glass.workspace import Workspace


def client(root):
    app=create_app(root);return app.test_client(),app.extensions['workspace'],{'X-Looking-Glass-Token':app.extensions['workspace'].token}


def test_commit_discussion_contract_context_replies_and_attachments(history_repo,monkeypatch):
    root=history_repo;c,ws,h=client(root);sha=git(root,'rev-parse','agent/review')
    payload={'git_target':{'kind':'commit','ref':sha},'body':'Review commit','author':'Altay'}
    assert c.post('/api/threads',json=payload).status_code==401
    created=c.post('/api/threads',headers=h,json=payload);assert created.status_code==201
    t=created.json;assert t['anchor_kind']=='commit' and t['commit_hash']==sha
    assert t['git_target']['ref']==sha and t['anchor_status']=='attached'
    monkeypatch.setattr(ws,'text',lambda _:(_ for _ in ()).throw(AssertionError('Git discussions must never read files')))
    assert c.get('/api/threads',headers=h).json[0]['id']==t['id']
    context=c.get(f'/api/threads/{t["id"]}?context_lines=5',headers=h).json['context']
    assert context['kind']=='commit' and 'Detailed review message' in context['content']
    reply=c.post(f'/api/threads/{t["id"]}/replies',headers=h,json={'body':'Reply','author':'Codex'})
    assert reply.status_code==201 and reply.json['messages'][-1]['commit_hash']==sha
    assert c.patch(f'/api/threads/{t["id"]}',headers=h,json={'resolved':True}).json['resolved']
    assert not c.patch(f'/api/threads/{t["id"]}',headers=h,json={'resolved':False}).json['resolved']
    attachment=c.post(f'/api/threads/{t["id"]}/attachments',headers=h,data={'file':(io.BytesIO(b'notes'),'notes.txt')});assert attachment.status_code==201
    assert c.get('/api/discussions',headers=h,query_string={'path':t['path']}).json['threads'][0]['id']==t['id']
    results=Workspace(root).query_threads(q='Review commit');assert results['total']==1 and results['threads'][0]['git_target']['ref']==sha
    assert c.delete(f'/api/threads/{t["id"]}',headers=h).json['deleted']
    assert not list(ws.attachments.directory.iterdir())


def test_branch_identity_survives_moves_and_deletion(history_repo):
    root=history_repo;c,ws,h=client(root);ref='refs/heads/agent/review';old=git(root,'rev-parse',ref)
    payload={'git_target':{'kind':'branch','ref':ref,'commit_hash':old},'body':'Review branch','author':'Altay'}
    t=c.post('/api/threads',headers=h,json=payload).json
    git(root,'update-ref',ref,git(root,'rev-parse','main'))
    assert c.post('/api/threads',headers=h,json=payload).status_code==409
    new=git(root,'rev-parse',ref);replied=ws.reply(t['id'],'After move','Agent')
    assert replied['commit_hash']==old and replied['messages'][-1]['commit_hash']==new
    original=ws.origins.read(t['id']);assert old in original['content']
    assert new in ws.origins.read(t['id'],replied['messages'][-1]['id'])['content']
    git(root,'branch','-D','agent/review')
    reread=Workspace(root).get_thread(t['id']);assert reread['anchor_status']=='attached'
    assert ws.reply(t['id'],'Still readable','Agent')['messages'][-1]['commit_hash']==old
    assert ws.thread_context(t['id'])['context']['ref']==ref


@pytest.mark.parametrize('target',[{'kind':'commit','ref':'HEAD'},{'kind':'commit','ref':'--all'}, {'kind':'commit','ref':'0'*40},{'kind':'branch','ref':'main'}, {'kind':'branch','ref':'refs/heads/missing'},{'kind':'source','ref':'main'},None])
def test_invalid_git_targets_are_rejected(history_repo,target):
    c,ws,h=client(history_repo)
    r=c.post('/api/threads',headers=h,json={'git_target':target,'body':'Invalid','author':'Altay'})
    assert r.status_code in (400,404) and ws.threads()==[]


def test_git_multipart_thread_and_mixed_anchor_rejection(history_repo):
    c,ws,h=client(history_repo);sha=git(history_repo,'rev-parse','HEAD')
    payload={'git_target':{'kind':'commit','ref':sha},'body':'','author':'Altay'}
    created=c.post('/api/threads',headers=h,data={'data':json.dumps(payload),'files':(io.BytesIO(b'image'),'image.png')})
    assert created.status_code==201 and created.json['attachments'][0]['message_id']==created.json['messages'][0]['id']
    assert c.post('/api/threads',headers=h,json={**payload,'path':'note.txt','body':'Mixed'}).status_code==400
