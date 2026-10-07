"""HTML source threads reuse the source API, reconciliation, and immutable origins."""
import pytest
from looking_glass.app import create_app
from looking_glass.workspace import Workspace


def test_html_source_thread_lifecycle(tmp_path):
    original='<!doctype html>\r\n<p>🪞 Before</p><p>Hello <b>world</b> &amp; friends.</p>'
    path=tmp_path/'report.html';path.write_bytes(original.encode())
    app=create_app(tmp_path);ws=app.extensions['workspace'];client=app.test_client()
    headers={'X-Looking-Glass-Token':ws.token}
    quote='Hello <b>world</b> &amp; friends.';start=original.index(quote)
    payload=dict(path='report.html',start=start,end=start+len(quote),body='Review HTML',author='Reviewer',version=ws.read('report.html')['version'])
    response=client.post('/api/threads',headers=headers,json=payload)
    assert response.status_code==201
    t=response.json;identifier=t['id']
    assert t['anchor_kind']=='source' and t['quote']==quote
    assert ws.thread_context(identifier,2)['context']['kind']=='source'
    original_context=client.get(f'/api/threads/{identifier}/original',headers=headers).json
    assert original_context['content']==original
    assert original_context['origin']['start']==start
    # Saving/moving surrounding markup preserves the raw source range.
    edited=original.replace('<p>Hello','<section>Introduction</section><p>Hello')
    ws.save('report.html',edited,ws.read('report.html')['version'])
    t=Workspace(tmp_path).get_thread(identifier)
    assert t['anchor_status']=='attached' and edited[t['start']:t['end']]==quote
    assert client.post('/api/threads',headers=headers,json=payload).status_code==409
    ws.reply(identifier,'Reply after editing','Agent')
    ws.update_thread(identifier,resolved=True);assert ws.get_thread(identifier)['resolved']
    ws.update_thread(identifier,resolved=False)
    path.write_text('<p>Replacement passage for review.</p>')
    assert ws.get_thread(identifier)['anchor_status']=='needs_reattachment'
    f=ws.read('report.html')
    ws.update_thread(identifier,start=3,end=f['content'].index('</p>'),version=f['version'])
    assert ws.get_thread(identifier)['quote']=='Replacement passage for review.'
    assert ws.origins.read(identifier)['content']==original
    assert len(ws.get_thread(identifier)['messages'])==2
    assert 'data-lg-' not in path.read_text()


@pytest.mark.parametrize('start,end',[(True,5),(-1,5),(3,10000),(5,3),(3,3)])
def test_html_source_rejects_invalid_offsets(tmp_path,start,end):
    (tmp_path/'a.html').write_text('<p>Hello</p>')
    app=create_app(tmp_path);ws=app.extensions['workspace'];client=app.test_client()
    response=client.post('/api/threads',headers={'X-Looking-Glass-Token':ws.token},json=dict(path='a.html',start=start,end=end,version=ws.read('a.html')['version'],body='Invalid',author='Reviewer'))
    assert response.status_code==400 and not ws.threads()


def test_html_preview_markers_do_not_leak_to_files_or_expose_credentials(tmp_path):
    original='<p>Hello &amp; world</p>';(tmp_path/'a.html').write_text(original)
    app=create_app(tmp_path);ws=app.extensions['workspace'];client=app.test_client()
    preview=client.post('/api/preview',headers={'X-Looking-Glass-Token':ws.token},json=dict(path='a.html',content='<p data-lg-test="0">Hello &amp; world</p>'))
    response=client.get(preview.json['url'])
    assert 'data-looking-glass-overlay' in response.text
    assert 'allow-same-origin' not in response.headers['Content-Security-Policy']
    assert ws.token not in response.text
    assert (tmp_path/'a.html').read_text()==original
