import copy
import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from looking_glass.app import create_app
from looking_glass.workspace import Problem, Workspace


def make_pdf(path, text='A passage to discuss', pages=3):
    writer = PdfWriter()
    for number in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 18 Tf 60 700 Td ({text} page {number+1}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    parent = writer.add_outline_item('Introduction', 0)
    writer.add_outline_item('Details', min(1, pages-1), parent=parent)
    writer.add_outline_item('Conclusion', pages-1)
    with path.open('wb') as output:
        writer.write(output)


@pytest.fixture
def pdf_workspace(tmp_path):
    make_pdf(tmp_path/'paper.pdf')
    return Workspace(tmp_path)


def test_bookmark_import_edit_delete_reorder_and_restart_leave_bytes_unchanged(pdf_workspace):
    ws = pdf_workspace
    raw = (ws.root/'paper.pdf').read_bytes()
    original = ws.pdfs.read('paper.pdf')
    assert [(b['title'], b['page'], b['level']) for b in original['bookmarks']] == [('Introduction', 1, 0), ('Details', 2, 1), ('Conclusion', 3, 0)]
    a, b, c = copy.deepcopy(original['bookmarks'])
    b.update(title='Renamed ✓', level=0)
    new = dict(id='new', title='Added', page=2, level=1)
    edited = ws.pdfs.save_bookmarks('paper.pdf', [c, b, new], 0, original['version'])
    assert edited['bookmark_revision'] == 1
    assert Workspace(ws.root).pdfs.read('paper.pdf')['bookmarks'] == [c, b, new]
    ws.pdfs.save_bookmarks('paper.pdf', [], 1, original['version'])
    assert Workspace(ws.root).pdfs.read('paper.pdf')['bookmarks'] == []
    assert (ws.root/'paper.pdf').read_bytes() == raw


def test_concurrent_bookmarks_and_external_file_changes(pdf_workspace):
    ws = pdf_workspace
    read = ws.pdfs.read('paper.pdf')
    other = Workspace(ws.root)
    ws.pdfs.save_bookmarks('paper.pdf', [], 0, read['version'])
    with pytest.raises(Problem, match='changed elsewhere'):
        other.pdfs.save_bookmarks('paper.pdf', read['bookmarks'], 0, read['version'])
    make_pdf(ws.root/'paper.pdf', text='Changed', pages=1)
    changed = ws.pdfs.read('paper.pdf')
    assert changed['bookmarks_stale'] and changed['bookmarks'] == []
    with pytest.raises(Problem, match='PDF changed'):
        ws.pdfs.save_bookmarks('paper.pdf', [], 1, read['version'])
    assert not ws.pdfs.save_bookmarks('paper.pdf', [], 1, changed['version'])['bookmarks_stale']


@pytest.mark.parametrize('change', [dict(page=0), dict(page=4), dict(page=True), dict(level=1), dict(level=-1), dict(title=''), dict(title='x'*501), dict(id='')])
def test_bookmark_validation(pdf_workspace, change):
    ws = pdf_workspace; read = ws.pdfs.read('paper.pdf')
    bookmark = {**read['bookmarks'][0], **change}
    with pytest.raises(Problem):
        ws.pdfs.save_bookmarks('paper.pdf', [bookmark], 0, read['version'])
    assert ws.pdfs.read('paper.pdf')['bookmark_revision'] == 0


def test_pdf_discussions_existing_lifecycle_context_and_reattachment(pdf_workspace):
    ws = pdf_workspace; read = ws.pdfs.read('paper.pdf')
    anchor = dict(page=2, quote='passage', rects=[[.1, .1, .3, .05]])
    thread = ws.pdfs.create_thread('paper.pdf', anchor, 'Discuss this', 'Human', read['version'])
    identifier = thread['id']
    assert thread['anchor_kind'] == 'pdf' and thread['anchor_status'] == 'attached'
    assert ws.thread_context(identifier)['context']['page'] == 2
    ws.reply(identifier, 'Reply', 'Agent')
    assert len(ws.get_thread(identifier)['messages']) == 2
    assert 'passage' in ws.origins.read(identifier)['content']
    ws.update_thread(identifier, resolved=True)
    assert ws.get_thread(identifier)['resolved']
    assert Workspace(ws.root).get_thread(identifier)['anchor_status'] == 'attached'
    make_pdf(ws.root/'paper.pdf', text='Other passage')
    assert ws.get_thread(identifier)['anchor_status'] == 'needs_reattachment'
    with pytest.raises(Problem, match='PDF changed'):
        ws.pdfs.reattach(identifier, anchor, read['version'])
    current = ws.pdfs.read('paper.pdf')
    ws.pdfs.reattach(identifier, dict(anchor, page=1), current['version'])
    assert ws.get_thread(identifier)['anchor_status'] == 'attached'
    assert ws.origins.read(identifier)['origin']['render_anchor']['page'] == 2
    ws.delete_thread(identifier)
    assert not ws.threads('paper.pdf')


def test_api_security_pdf_reads_annotations_and_no_file_writes(tmp_path):
    make_pdf(tmp_path/'paper.PDF'); raw = (tmp_path/'paper.PDF').read_bytes()
    app = create_app(tmp_path); client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    assert client.get('/api/pdf?path=paper.PDF').status_code == 401
    read = client.get('/api/pdf?path=paper.PDF', headers=headers).json
    assert client.get('/api/pdf', query_string=dict(path='paper.PDF',version=read['version'],bookmark_revision=0), headers=headers).status_code == 304
    assert client.get('/api/binary?path=paper.PDF', headers=headers).data == raw
    assert client.get('/api/stat?path=paper.PDF', headers=headers).json['limit'] == 64*1024*1024
    data = dict(path='paper.PDF', version=read['version'], pdf_anchor=dict(page=1, quote='passage', rects=[[.1,.1,.2,.02]]), body='Comment', author='User')
    response = client.post('/api/threads', headers=headers, json=data)
    assert response.status_code == 201
    identifier = response.json['id']
    assert client.patch(f'/api/threads/{identifier}', headers=headers, json=dict(pdf_anchor=data['pdf_anchor'], version=read['version'])).status_code == 200
    data['pdf_anchor']['rects'] = [[0, 0, float('inf'), .1]]
    assert client.post('/api/threads', headers=headers, json=data).status_code == 400
    assert client.put('/api/file', headers=headers, json=dict(path='paper.PDF', content='overwrite', version=read['version'])).status_code == 415
    assert client.post('/api/reviews', headers=headers, json=dict(path='paper.PDF', version=read['version'])).status_code == 415
    assert client.get('/api/pdf?path=../paper.PDF', headers=headers).status_code == 403
    assert (tmp_path/'paper.PDF').read_bytes() == raw


def test_malformed_encrypted_and_oversized_pdf(tmp_path):
    ws = Workspace(tmp_path)
    (tmp_path/'bad.pdf').write_bytes(b'not a PDF')
    with pytest.raises(Problem) as error:
        ws.pdfs.read('bad.pdf')
    assert error.value.status == 415
    writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.encrypt('password')
    with (tmp_path/'encrypted.pdf').open('wb') as output: writer.write(output)
    with pytest.raises(Problem, match='Password'):
        ws.pdfs.read('encrypted.pdf')
    with (tmp_path/'large.pdf').open('wb') as output: output.truncate(64*1024*1024+1)
    with pytest.raises(Problem) as error:
        ws.pdfs.read('large.pdf')
    assert error.value.status == 413
