import subprocess
import pytest
from looking_glass.app import create_app
from looking_glass.revisions import Revisions
from looking_glass.workspace import Workspace, Problem

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()

@pytest.fixture
def history_repo(tmp_path):
    git(tmp_path,'init','-b','main');git(tmp_path,'config','user.name','Altay');git(tmp_path,'config','user.email','altay@example.invalid')
    (tmp_path/'note.txt').write_text('Original passage.\n');git(tmp_path,'add','note.txt');git(tmp_path,'commit','-m','Initial')
    git(tmp_path,'switch','-c','agent/review');git(tmp_path,'config','user.name','Codex');git(tmp_path,'config','user.email','codex@example.invalid')
    (tmp_path/'agent.txt').write_text('agent change');git(tmp_path,'add','agent.txt');git(tmp_path,'commit','-m','Agent review\n\nDetailed review message\nwith multiple lines.')
    git(tmp_path,'switch','main');git(tmp_path,'config','user.name','Altay');git(tmp_path,'config','user.email','altay@example.invalid')
    (tmp_path/'user.txt').write_text('user change');git(tmp_path,'add','user.txt');git(tmp_path,'commit','-m','User edit')
    git(tmp_path,'merge','--no-ff','agent/review','-m','Merge review')
    return tmp_path

def test_history_merges_filter_pagination_and_read_only(history_repo):
    root=history_repo;ws=Workspace(root);rev=Revisions(ws)
    before=git(root,'status','--porcelain');first=rev.history(limit=2)
    assert first['commits'][0]['subject']=='Merge review'
    assert len(first['commits'][0]['parents'])==2
    second=rev.history(limit=2,offset=first['next_offset'],tips=first['tips'])
    assert len({c['hash'] for c in first['commits']+second['commits']})==4
    topic=rev.history(['refs/heads/agent/review'])
    assert [c['subject'] for c in topic['commits']]==['Agent review','Initial']
    assert 'Detailed review message\nwith multiple lines.' in topic['commits'][0]['message']
    assert topic['commits'][0]['committer']=='Codex'
    assert rev.history([])['commits']==[]
    git(root,'update-ref','refs/remotes/origin/main',git(root,'rev-parse','main'))
    assert 'origin/main' in [b['name'] for b in rev.history()['branches']]
    assert git(root,'status','--porcelain')==before
    for options in ({'branches':['--all']},{'limit':1000},{'offset':-1},{'tips':['HEAD']}):
        with pytest.raises(Problem):rev.history(**options)
    app=create_app(root);c=app.test_client();h={'X-Looking-Glass-Token':ws.token}
    assert c.get('/api/git/history').status_code==401
    assert c.get('/api/git/history?branch=refs/heads/agent/review',headers=h).json['commits'][0]['subject']=='Agent review'

def test_history_no_repository_and_empty_repository(tmp_path):
    rev=Revisions(Workspace(tmp_path));assert rev.history()['repository'] is False
    git(tmp_path,'init');assert rev.history()['commits']==[]
