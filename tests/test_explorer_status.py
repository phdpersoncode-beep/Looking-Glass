import subprocess
from looking_glass.app import create_app
from looking_glass.workspace import Workspace
from looking_glass.revisions import Revisions


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)


def test_explorer_git_states_ignore_rules_staging_and_status_only_etag(tmp_path):
    git(tmp_path,'init');git(tmp_path,'config','user.name','Test');git(tmp_path,'config','user.email','test@example.invalid')
    for name in ['clean.txt','changed.txt','later-ignored.txt']:(tmp_path/name).write_text('Original')
    (tmp_path/'.gitignore').write_text('ignored/\n*.log\n')
    git(tmp_path,'add','.');git(tmp_path,'commit','-m','Initial')
    (tmp_path/'new').mkdir();(tmp_path/'new/über file.txt').write_text('New')
    (tmp_path/'ignored').mkdir();(tmp_path/'ignored/a.txt').write_text('Ignored')
    (tmp_path/'trace.log').write_text('Ignored log');(tmp_path/'staged.txt').write_text('Staged');git(tmp_path,'add','staged.txt')
    (tmp_path/'changed.txt').write_text('Changed')
    (tmp_path/'.gitignore').write_text('ignored/\n*.log\nlater-ignored.txt\n')
    app=create_app(tmp_path);client=app.test_client();ws=app.extensions['workspace']
    index=(tmp_path/'.git/index').read_bytes()
    paths=ws.files()+ws.folders();states=Revisions(ws).explorer_status(paths)
    assert (tmp_path/'.git/index').read_bytes()==index
    assert states['changed.txt']=='modified' and states['staged.txt']=='new'
    assert states['new/über file.txt']==states['new']=='new'
    assert states['ignored/a.txt']==states['ignored']==states['trace.log']=='ignored'
    assert 'clean.txt' not in states and 'later-ignored.txt' not in states
    headers={'X-Looking-Glass-Token':ws.token};first=client.get('/fragments/files',headers=headers)
    assert 'data-git-status="modified" data-path="changed.txt"' in first.text
    assert client.get('/fragments/files',headers={**headers,'If-None-Match':first.headers['ETag']}).status_code==304
    (tmp_path/'changed.txt').write_text('Original')
    second=client.get('/fragments/files',headers={**headers,'If-None-Match':first.headers['ETag']})
    assert second.status_code==200 and second.headers['ETag']!=first.headers['ETag']
    assert 'data-git-status="" data-path="changed.txt"' in second.text


def test_explorer_status_nested_workspace_and_rename_with_unusual_names(tmp_path):
    git(tmp_path,'init');git(tmp_path,'config','user.name','Test');git(tmp_path,'config','user.email','test@example.invalid')
    (tmp_path/'project').mkdir();(tmp_path/'project/old name.txt').write_text('Old');(tmp_path/'outside.txt').write_text('Outside')
    git(tmp_path,'add','.');git(tmp_path,'commit','-m','Initial')
    git(tmp_path,'mv','project/old name.txt','project/new\nname.txt')
    (tmp_path/'outside.txt').write_text('Changed outside');(tmp_path/'project/new.txt').write_text('New')
    ws=Workspace(tmp_path/'project');states=Revisions(ws).explorer_status(ws.files())
    assert states=={'new\nname.txt':'modified','new.txt':'new'}
    plain=tmp_path/'plain';plain.mkdir()
    # A workspace in the same repository still uses its own path prefix.
    assert Revisions(Workspace(plain)).explorer_status([])=={}
