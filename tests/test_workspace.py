from pathlib import Path
from urllib.parse import urlencode
import pytest
from looking_glass.app import create_app
from looking_glass.workspace import Workspace, Problem
from looking_glass.anchors import relocate


@pytest.fixture
def ws(tmp_path):
    (tmp_path/'notes.md').write_text('Before\n\nA useful passage for review.\n\nAfter\n')
    return Workspace(tmp_path)


def thread(ws):
    file = ws.read('notes.md')
    quote = 'A useful passage for review.'
    start = file['content'].index(quote)
    return ws.create_thread('notes.md',start,start+len(quote),'Explain this.','Altay',file['version'])


def test_save_conflicts_and_persistence(ws):
    t = thread(ws)
    old = ws.read('notes.md')
    ws.save('notes.md','New heading\n'+old['content'],old['version'])
    assert ws.get_thread(t['id'])['start'] == t['start']+len('New heading\n')
    ws.reply(t['id'],'Here is why.','Codex')
    restarted = Workspace(ws.root)
    assert len(restarted.get_thread(t['id'])['messages']) == 2
    assert restarted.token == ws.token
    version = restarted.read('notes.md')['version']
    (ws.root/'notes.md').write_text('external edit')
    with pytest.raises(Problem,match='changed on disk'):
        restarted.save('notes.md','my draft',version)
    assert (ws.root/'notes.md').read_text() == 'external edit'
    assert restarted.get_thread(t['id'])['anchor_status'] == 'needs_reattachment'


def test_anchor_edits_inside_and_deletion(ws):
    t=thread(ws)
    f=ws.read('notes.md')
    changed=f['content'].replace('useful','very useful')
    ws.save('notes.md',changed,f['version'])
    assert ws.get_thread(t['id'])['quote']=='A very useful passage for review.'
    f=ws.read('notes.md')
    ws.save('notes.md',f['content'].replace('A very useful passage for review.',''),f['version'])
    assert ws.get_thread(t['id'])['anchor_status']=='needs_reattachment'
    f=ws.read('notes.md')
    attached=ws.update_thread(t['id'],start=0,end=6,version=f['version'])
    assert attached['quote']=='Before'
    assert attached['anchor_status']=='attached'


def test_ambiguous_move_is_orphaned():
    assert relocate('left abc right','abc\nabc',5,8) is None


def test_ordinary_boundary_edits_stay_attached():
    old='before\nA useful passage for review.\nafter'
    start=old.index('A useful')
    end=old.index('\nafter')
    new=old.replace('A useful','This useful').replace('review.','discussion.')
    positions=relocate(old,new,start,end)
    assert positions is not None
    assert new[slice(*positions)]=='This useful passage for discussion.'


def test_unicode_and_stale_anchor(ws):
    f=ws.read('notes.md')
    ws.save('notes.md','🪞 München passage',f['version'])
    f=ws.read('notes.md')
    t=ws.create_thread('notes.md',2,9,'Unicode','Altay',f['version'])
    assert t['quote']=='München'
    (ws.root/'notes.md').write_text('changed')
    with pytest.raises(Problem):
        ws.create_thread('notes.md',2,9,'stale','Codex',f['version'])


def test_traversal_symlinks_and_metadata_blocked(ws,tmp_path):
    (ws.root/'link.md').symlink_to(ws.root/'notes.md')
    for path in ('../outside','.looking-glass/token','link.md',str(ws.root/'notes.md'),'/tmp/../etc/passwd'):
        with pytest.raises(Problem):
            ws.read(path)
    assert 'link.md' not in ws.files()
    assert not any('.looking-glass' in f for f in ws.files())


def test_outside_files_use_canonical_absolute_keys(ws,tmp_path_factory):
    outside=tmp_path_factory.mktemp('outside')/'session.jsonl'
    outside.write_text('{"a": 1}\n')
    (outside.parent/'alias.jsonl').symlink_to(outside)
    assert ws.locate(str(outside.parent/'alias.jsonl'))==str(outside)
    assert ws.locate(str(ws.root/'notes.md'))=='notes.md'
    assert ws.locate('notes.md')=='notes.md'
    with pytest.raises(Problem):
        ws.read(str(outside.parent/'alias.jsonl'))
    with pytest.raises(Problem):
        ws.locate(str(outside.parent/'missing.md'))
    file=ws.read(str(outside))
    t=ws.create_thread(str(outside),1,4,'Outside comment.','Altay',file['version'])
    assert Workspace(ws.root).get_thread(t['id'])['quote']=='"a"'
    assert str(outside) not in ws.files()


def test_switch_workspace_and_list_directories(ws,tmp_path_factory):
    other=tmp_path_factory.mktemp('other')
    (other/'b').mkdir();(other/'.hidden').mkdir();(other/'A').mkdir();(other/'file.md').write_text('Other.\n')
    app=create_app(ws.root)
    client=app.test_client()
    headers={'X-Looking-Glass-Token':ws.token}
    listing=client.get('/api/directories?'+urlencode({'path':str(other)}),headers=headers).json
    assert listing['directories']==['A','b','.hidden'] and listing['parent']==str(other.parent)
    assert client.get('/api/directories?path=/no/such/dir',headers=headers).status_code==404
    assert client.post('/api/workspace',headers=headers,json={'path':''}).status_code==400
    assert client.post('/api/workspace',headers=headers,json={'path':str(other)}).json['root']==str(other)
    assert client.get('/api/workspace',headers=headers).status_code==401
    token=(other/'.looking-glass'/'token').read_text().strip()
    assert client.get('/api/workspace',headers={'X-Looking-Glass-Token':token}).json['files']==['file.md']


def test_http_auth_preview_and_replies(ws):
    app=create_app(ws.root)
    client=app.test_client()
    headers={'X-Looking-Glass-Token':ws.token}
    assert client.get('/api/threads').status_code==401
    assert client.get('/api/threads',headers={**headers,'Origin':'null'}).status_code==403
    assert client.get('/api/threads',headers={**headers,'Host':'evil.example'}).status_code==400
    f=client.get('/api/file?path=notes.md',headers=headers).json
    response=client.post('/api/threads',headers=headers,json=dict(path='notes.md',start=0,end=6,body='<script>evil</script>',author='Codex',version=f['version']))
    assert response.status_code==201
    id=response.json['id']
    assert client.post(f'/api/threads/{id}/replies',headers=headers,json=dict(body='reply',author='Altay')).status_code==201
    assert client.patch(f'/api/threads/{id}',headers=headers,json={'resolved':True}).json['resolved']
    assert not client.patch(f'/api/threads/{id}',headers=headers,json={'resolved':False}).json['resolved']
    fragment=client.get('/fragments/threads?path=notes.md',headers=headers).text
    assert '&lt;script&gt;' in fragment and '<script>evil' not in fragment
    (ws.root/'report.html').write_text('<button>Interactive</button><script>parent.document</script>')
    cap=client.post('/api/preview',headers=headers,json={'path':'report.html','content':(ws.root/'report.html').read_text()}).json['url']
    assert ws.token not in cap
    preview=client.get(cap)
    assert preview.status_code==200
    assert 'sandbox allow-scripts' in preview.headers['Content-Security-Policy']
    assert 'allow-same-origin' not in preview.headers['Content-Security-Policy']
    assert client.post('/api/preview',json={'path':'report.html','content':'x'}).status_code==401
    assert client.put('/api/file',headers=headers,json=[]).status_code==400


def test_line_endings_and_mode_preserved(ws):
    path=ws.root/'crlf.sh'
    path.write_bytes(b'#!/bin/bash\r\necho hi\r\n')
    path.chmod(0o755)
    file=ws.read('crlf.sh')
    assert '\r\n' in file['content']
    ws.save('crlf.sh',file['content'].replace('hi','hello'),file['version'])
    assert b'\r\n' in path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o755


def test_delete_comments_and_threads(ws):
    t=thread(ws)
    t=ws.reply(t['id'],'Keep this reply.','Agent')
    other=thread(ws)
    client=create_app(ws.root).test_client()
    headers={'X-Looking-Glass-Token':ws.token}
    route=f"/api/threads/{t['id']}/messages/{t['messages'][0]['id']}"
    assert client.delete(route).status_code==401
    assert client.delete(f"/api/threads/{other['id']}/messages/{t['messages'][0]['id']}",headers=headers).status_code==404
    assert client.delete(route,headers=headers).json=={'deleted':True}
    restarted=Workspace(ws.root)
    assert [m['body'] for m in restarted.get_thread(t['id'])['messages']]==['Keep this reply.']
    assert client.delete(f"/api/threads/{t['id']}/messages/{t['messages'][1]['id']}",headers=headers).status_code==200
    with pytest.raises(Problem,match='Thread not found'):
        restarted.get_thread(t['id'])
    assert client.delete(f"/api/threads/{other['id']}",headers=headers).status_code==200
    assert restarted.threads()==[]
    with restarted.connection() as db:
        assert db.execute('SELECT count(*) FROM messages').fetchone()[0]==0


def test_rendered_html_anchors_persist_and_require_current_version(ws):
    (ws.root/'report.html').write_text('<p>Hello <strong>world</strong> &amp; friends.</p>')
    client=create_app(ws.root).test_client()
    headers={'X-Looking-Glass-Token':ws.token}
    file=ws.read('report.html')
    anchor=dict(quote='Hello world & friends.',prefix='',suffix='')
    response=client.post('/api/threads',headers=headers,json=dict(path='report.html',render_anchor=anchor,body='Clarify this.',author='Altay',version=file['version']))
    assert response.status_code==201
    t=response.json
    assert t['anchor_kind']=='rendered' and t['render_anchor']==anchor
    assert Workspace(ws.root).get_thread(t['id'])['quote']==anchor['quote']
    saved=ws.save('report.html','<article><p>Hello <em>world</em> &amp; friends.</p></article>',file['version'])
    assert ws.get_thread(t['id'])['render_anchor']==anchor
    assert client.patch(f"/api/threads/{t['id']}",headers=headers,json=dict(render_attached=False,version=file['version'])).status_code==409
    assert client.patch(f"/api/threads/{t['id']}",headers=headers,json=dict(render_attached=False,version=saved['version'])).json['anchor_status']=='needs_reattachment'
    new_anchor=dict(quote='Hello world',prefix='',suffix=' & friends.')
    assert client.patch(f"/api/threads/{t['id']}",headers=headers,json=dict(render_anchor=new_anchor,version=saved['version'])).json['anchor_status']=='attached'
    assert client.patch(f"/api/threads/{t['id']}",headers=headers,json=dict(start=0,end=3,version=saved['version'])).status_code==400
    assert client.post('/api/threads',headers=headers,json=dict(path='notes.md',render_anchor=anchor,body='No.',author='Altay',version=ws.read('notes.md')['version'])).status_code==400


def test_thread_query_api_validation_and_context(ws):
    t=thread(ws)
    ws.reply(t['id'],'Use 100% of 🪞 examples.','Agent')
    other=thread(ws)
    ws.update_thread(other['id'],resolved=True)
    client=create_app(ws.root).test_client()
    headers={'X-Looking-Glass-Token':ws.token}
    assert client.get('/api/project',headers=headers).json=={'root':str(ws.root)}
    # Legacy browser/API callers still receive the original full array.
    assert len(client.get('/api/threads',headers=headers).json)==2
    found=client.get('/api/threads?'+urlencode(dict(q='100%',status='open',author='agent',summary='false')),headers=headers).json
    assert found['total']==1 and len(found['threads'][0]['messages'])==2
    assert ws.query_threads(q='useful')['total']==2
    assert ws.query_threads(q='%')['total']==1
    assert ws.query_threads(offset=99)['next_offset'] is None
    for query in ('status=invalid','anchor_status=invalid','limit=0','limit=1001','limit=x','offset=-1','summary=maybe'):
        assert client.get('/api/threads?'+query,headers=headers).status_code==400
    context=client.get(f"/api/threads/{t['id']}?context_lines=1",headers=headers).json['context']
    assert context['start_line']==3 and context['content']=='\nA useful passage for review.\n\n'
    for value in ('-1','101','no'):
        assert client.get(f"/api/threads/{t['id']}?context_lines={value}",headers=headers).status_code==400
    (ws.root/'notes.md').unlink()
    detached=ws.thread_context(t['id'])
    assert detached['context']['kind']=='unavailable'
    assert ws.query_threads(anchor_status='needs_reattachment')['total']==2


def test_context_unicode_crlf_multiline_and_rendered(ws):
    (ws.root/'lines.txt').write_bytes('First\r\n🪞 Quote\r\nSecond\r\nLast'.encode())
    file=ws.read('lines.txt')
    quote='🪞 Quote\r\nSecond\r\n'
    start=file['content'].index(quote)
    t=ws.create_thread('lines.txt',start,start+len(quote),'Question','Altay',file['version'])
    context=ws.thread_context(t['id'],0)['context']
    assert context['start_line']==2 and context['end_line']==3
    assert context['content']==quote
    (ws.root/'unicode.txt').write_text('Before\nA\u2028passage\nAfter')
    file=ws.read('unicode.txt')
    quote='A\u2028passage'
    t=ws.create_thread('unicode.txt',7,7+len(quote),'Question','Altay',file['version'])
    context=ws.thread_context(t['id'],0)['context']
    assert context['start_line']==context['end_line']==2
    assert context['content']==quote+'\n'
    (ws.root/'report.html').write_text('<p>Hello world</p>')
    file=ws.read('report.html')
    anchor=dict(quote='Hello world',prefix='',suffix='')
    t=ws.create_rendered_thread('report.html',anchor,'Question','Altay',file['version'])
    assert ws.thread_context(t['id'])['context']==dict(kind='rendered',**anchor)
