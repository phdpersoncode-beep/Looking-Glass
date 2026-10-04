"""Fast API contracts for discussion workflow changes."""
import io
import pytest
from looking_glass.app import create_app
from looking_glass.workspace import Workspace

@pytest.fixture
def api(tmp_path):
    (tmp_path/'note.txt').write_text('A passage to discuss.\n')
    app=create_app(tmp_path);ws=app.extensions['workspace'];client=app.test_client()
    headers={'X-Looking-Glass-Token':ws.token}
    f=ws.read('note.txt');t=ws.create_thread('note.txt',0,9,'Review','Tester',f['version'])
    return tmp_path,ws,client,headers,t

def test_attachment_roundtrip_and_cleanup(api,monkeypatch):
    root,ws,c,h,t=api
    values=[('visual.svg',b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'),('mesh.stl',b'\0\1\2'),('data.json',b'{"x": 1}')]
    for name,data in values:
        r=c.post(f'/api/threads/{t["id"]}/attachments',headers=h,data={'file':(io.BytesIO(data),name)})
        assert r.status_code==201;r=r.json
        assert r['name']==name and r['size']==len(data) and 'storage_key' not in r
        assert c.get(f'/api/attachments/{r["id"]}').status_code==401
        result=c.get(f'/api/attachments/{r["id"]}',headers=h)
        assert result.data==data and result.headers['Content-Disposition'].startswith('attachment;')
        assert c.patch(f'/api/attachments/{r["id"]}',headers=h,json={'name':'../token'}).status_code==400
        assert c.patch(f'/api/attachments/{r["id"]}',headers=h,json={'name':'feedback '+name}).json['name']=='feedback '+name
    assert len(Workspace(root).get_thread(t['id'])['attachments'])==3
    assert c.post(f'/api/threads/{t["id"]}/attachments',headers=h,data={'file':(io.BytesIO(b'x'),'../bad')}).status_code==400
    import looking_glass.attachments as attachments
    monkeypatch.setattr(attachments,'MAX_ATTACHMENT',2)
    assert c.post(f'/api/threads/{t["id"]}/attachments',headers=h,data={'file':(io.BytesIO(b'big'),'large')}).status_code==413
    assert len(list(ws.attachments.directory.iterdir()))==3
    assert c.delete(f'/api/attachments/{r["id"]}',headers=h).json=={'deleted':True}
    c.delete(f'/api/threads/{t["id"]}/messages/{t["messages"][0]["id"]}',headers=h)
    assert not list(ws.attachments.directory.iterdir())
    assert c.get(f'/api/attachments/{r["id"]}',headers=h).status_code==404

def test_discussion_refresh_avoids_source_reads_and_revalidates(api,monkeypatch):
    root,ws,c,h,t=api
    def forbidden(path):raise AssertionError('Discussion browsing reread a document')
    monkeypatch.setattr(ws,'text',forbidden)
    first=c.get('/api/discussions?scope=all',headers=h)
    assert first.status_code==200 and first.json['threads'][0]['id']==t['id']
    assert first.json['index'][0]['path']=='note.txt'
    assert c.get('/api/thread-index',headers=h).json[0]['id']==t['id']
    assert c.get('/api/discussions?scope=all',headers={**h,'If-None-Match':first.headers['ETag']}).status_code==304
    with ws.connection() as db:db.execute('INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)',(t['id'],'Agent','New reply'))
    changed=c.get('/api/discussions?scope=all',headers={**h,'If-None-Match':first.headers['ETag']})
    assert changed.status_code==200 and 'New reply' in changed.json['html']
    assert c.get('/api/discussions').status_code==401

def test_unchanged_file_poll_does_not_read_or_write(api,monkeypatch):
    import os
    root,ws,c,h,t=api
    first=c.get('/api/file?path=note.txt',headers=h).json
    original=ws.text
    monkeypatch.setattr(ws,'text',lambda path:(_ for _ in ()).throw(AssertionError('Unchanged file read')))
    assert c.get('/api/file',query_string={'path':'note.txt','version':first['version']},headers=h).status_code==304
    monkeypatch.setattr(ws,'text',original)
    p=root/'note.txt';info=p.stat();p.write_text('B'+p.read_text()[1:]);os.utime(p,ns=(info.st_atime_ns,info.st_mtime_ns))
    changed=c.get('/api/file',query_string={'path':'note.txt','version':first['version']},headers=h)
    assert changed.status_code==200 and changed.json['content'].startswith('B')
    assert changed.json['version']!=first['version']
    assert ws.get_thread(t['id'])['quote'].startswith('B')


def test_file_tree_revalidation_and_scan_failure(api, monkeypatch):
    import os
    root, ws, c, h, _ = api
    first = c.get('/fragments/files', headers=h)
    assert first.status_code == 200 and b'note.txt' in first.data
    conditional = {**h, 'If-None-Match': first.headers['ETag']}
    assert c.get('/fragments/files', headers=conditional).status_code == 304
    (root/'new.txt').write_text('New file')
    changed = c.get('/fragments/files', headers=conditional)
    assert changed.status_code == 200 and b'new.txt' in changed.data
    original = os.scandir
    def fail_scan(path):
        if str(path) == str(root):
            raise PermissionError('Temporary scan failure')
        return original(path)
    monkeypatch.setattr(os, 'scandir', fail_scan)
    failed = c.get('/fragments/files', headers=h)
    assert failed.status_code == 409
    assert 'Temporary scan failure' in failed.json['error']
    monkeypatch.setattr(os, 'scandir', original)
    (root/'note.txt').unlink(); (root/'new.txt').unlink()
    empty = c.get('/fragments/files', headers=conditional)
    assert empty.status_code == 200 and b'No files in this directory.' in empty.data
