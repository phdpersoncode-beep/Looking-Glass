import sqlite3
import pytest
from test_history import history_repo, git
from looking_glass.app import create_app
from looking_glass.workspace import Workspace

def test_immutable_origins_replies_reattachment_deletion_and_restart(history_repo):
    root=history_repo;ws=Workspace(root);head=git(root,'rev-parse','HEAD');file=ws.read('note.txt')
    t=ws.create_thread('note.txt',0,8,'Review','Altay',file['version']);id=t['id']
    assert t['commit_hash']==head==t['messages'][0]['commit_hash']
    assert ws.origins.read(id)['content']=='Original passage.\n'
    (root/'note.txt').write_text('Prefix\nOriginal passage.\n');git(root,'add','note.txt');git(root,'commit','-m','Move reviewed text')
    t=ws.reply(id,'Second review','Agent');reply=t['messages'][-1]
    assert t['start']==7 and t['commit_hash']==head
    assert reply['commit_hash']==git(root,'rev-parse','HEAD')!=head
    assert ws.origins.read(id,reply['id'])['content']=='Prefix\nOriginal passage.\n'
    current=ws.read('note.txt');ws.update_thread(id,start=16,end=23,version=current['version'])
    assert ws.origins.read(id)['origin']['quote']=='Original'
    (root/'note.txt').unlink();git(root,'add','note.txt');git(root,'commit','-m','Delete reviewed file')
    t=ws.reply(id,'Discussion still matters','Agent')
    assert t['anchor_status']=='needs_reattachment' and len(t['messages'])==3
    assert t['messages'][-1]['commit_hash']==git(root,'rev-parse','HEAD')
    assert t['messages'][-1]['origin']['provenance']=='inherited'
    assert Workspace(root).origins.read(id)['content']=='Original passage.\n'
    app=create_app(root);c=app.test_client();h={'X-Looking-Glass-Token':ws.token}
    assert c.get(f'/api/threads/{id}/original').status_code==401
    assert c.get(f'/api/threads/{id}/original',headers=h).json['content']=='Original passage.\n'
    assert c.get(f'/api/threads/{id}/messages/{reply["id"]}/original',headers=h).json['origin']['commit_hash']==reply['commit_hash']
    assert c.get(f'/api/threads/{id}/messages/999/original',headers=h).status_code==404
    with ws.connection() as db:
        assert db.execute('SELECT count(*) FROM review_versions').fetchone()[0]==2
    ws.delete_thread(id)
    with ws.connection() as db:
        assert db.execute('SELECT count(*) FROM review_versions').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM review_origins').fetchone()[0]==0

def test_uncommitted_content_rendered_and_no_git_origins(history_repo,tmp_path_factory):
    root=history_repo;ws=Workspace(root)
    (root/'note.txt').write_text('Uncommitted source.\n');f=ws.read('note.txt')
    t=ws.create_thread('note.txt',0,11,'Dirty review','Agent',f['version'])
    assert t['commit_hash']==git(root,'rev-parse','HEAD')
    assert ws.origins.read(t['id'])['content']=='Uncommitted source.\n'
    (root/'report.html').write_text('<p>Rendered passage</p>');f=ws.read('report.html')
    rendered=ws.create_rendered_thread('report.html',dict(quote='Rendered passage',prefix='',suffix=''),'Review','Agent',f['version'])
    (root/'report.html').unlink()
    assert ws.origins.read(rendered['id'])['origin']['render_anchor']['quote']=='Rendered passage'
    outside=tmp_path_factory.mktemp('no-repo');(outside/'note.txt').write_text('Outside')
    no_git=Workspace(outside);f=no_git.read('note.txt');t=no_git.create_thread('note.txt',0,7,'Review','Agent',f['version'])
    assert t['commit_hash'] is None and no_git.origins.read(t['id'])['content']=='Outside'

def test_legacy_database_migrates_without_inventing_past_commit(tmp_path):
    meta=tmp_path/'.looking-glass';meta.mkdir()
    with sqlite3.connect(meta/'state.sqlite3') as db:
        db.executescript("""
        CREATE TABLE snapshots(path TEXT PRIMARY KEY,content TEXT NOT NULL);
        CREATE TABLE threads(id INTEGER PRIMARY KEY,path TEXT,start INTEGER,end INTEGER,quote TEXT,anchor_status TEXT DEFAULT 'attached',resolved INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE messages(id INTEGER PRIMARY KEY,thread_id INTEGER,author TEXT,body TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO snapshots VALUES('gone.txt','A lost passage.');
        INSERT INTO threads(id,path,start,end,quote) VALUES(1,'gone.txt',2,6,'lost');
        INSERT INTO messages(id,thread_id,author,body) VALUES(1,1,'Altay','Keep this');
        """)
    ws=Workspace(tmp_path);t=ws.get_thread(1)
    assert t['messages'][0]['body']=='Keep this' and t['anchor_status']=='needs_reattachment'
    assert t['origin']['provenance']=='recovered'
    original=ws.origins.read(1);assert original['content']=='A lost passage.'
    assert Workspace(tmp_path).origins.read(1)==original
