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
