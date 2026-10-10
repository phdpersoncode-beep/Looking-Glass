"""Cross-feature contracts: ordinary files, review, discussions and Git together."""
import io
import json
import subprocess

import pytest
from looking_glass.app import create_app
from looking_glass.workspace import Workspace, Problem
from looking_glass.revisions import Revisions


@pytest.mark.parametrize('name,original', [
    ('notes.md', '# München 🪞\r\n\r\n7. Review passage\r\n'),
    ('script.py', '# München 🪞\r\nvalue = 12\r\n'),
    ('report.html', '<p>München 🪞 &amp; review</p>\r\n'),
    ('plain.txt', 'München 🪞 review passage\r\n'),
])
def test_discussion_lifecycle_across_review_approval_and_restart(tmp_path, name, original):
    path = tmp_path / name
    path.write_bytes(original.encode())
    app = create_app(tmp_path)
    ws = app.extensions['workspace']
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': ws.token}
    file = ws.read(name)
    start = original.index('München')
    thread = ws.create_thread(name, start, start + len('München'), 'Initial question', 'Altay', file['version'])
    origin = ws.origins.read(thread['id'])
    draft = ws.reviews.start(name, file['version'])
    prefix = 'Agent 🧠\r\n'
    draft = ws.reviews.update(draft['id'], draft['version'],
                              [dict(start=0, end=0, insert=prefix)], 'Codex', 'agent')
    new = ws.reviews.create_thread(draft['id'], draft['version'], 0, len('Agent 🧠'), 'Draft only', 'Altay')
    assert [t['id'] for t in ws.threads(name)] == [thread['id']]
    assert ws.get_thread(thread['id'], review=draft['id'])['start'] == start + len(prefix)
    assert ws.get_thread(thread['id'])['start'] == start
    reply = client.post(f'/api/threads/{thread["id"]}/replies', headers=headers, data={
        'data': json.dumps(dict(body='Attached draft reply', author='Codex', review_id=draft['id'])),
        'files': (io.BytesIO(b'attachment bytes'), 'evidence.txt'),
    })
    assert reply.status_code == 201
    message = reply.json['messages'][-1]
    attachment = reply.json['attachments'][0]
    reply_origin = ws.origins.read(thread['id'], message['id'])
    assert reply_origin['content'] == draft['content']
    edited = client.patch(f'/api/threads/{thread["id"]}/messages/{message["id"]}',
                          headers=headers, json={'body': 'Revised explanation'})
    assert edited.status_code == 200
    assert ws.origins.read(thread['id'], message['id']) == reply_origin
    ws.update_thread(thread['id'], resolved=True)
    restarted = Workspace(tmp_path)
    assert restarted.reviews.read(draft['id'])['content'] == prefix + original
    assert restarted.get_thread(thread['id'])['resolved']
    assert path.read_bytes() == original.encode()
    restarted.reviews.approve(draft['id'], draft['version'])
    restarted = Workspace(tmp_path)
    assert path.read_bytes() == (prefix + original).encode()
    assert {t['id'] for t in restarted.threads(name)} == {thread['id'], new['id']}
    assert restarted.get_thread(thread['id'])['start'] == start + len(prefix)
    assert restarted.get_thread(thread['id'])['quote'] == 'München'
    assert restarted.get_thread(thread['id'])['resolved']
    assert restarted.origins.read(thread['id']) == origin
    assert restarted.origins.read(thread['id'], message['id']) == reply_origin
    assert client.get(f'/api/attachments/{attachment["id"]}', headers=headers).data == b'attachment bytes'
    assert restarted.query_threads(q='Revised explanation', status='resolved')['total'] == 1
    restarted.delete_message(thread['id'], message['id'])
    assert len(restarted.get_thread(thread['id'])['messages']) == 1
    assert client.get(f'/api/attachments/{attachment["id"]}', headers=headers).status_code == 404
    assert restarted.origins.read(thread['id']) == origin


def test_approval_then_selected_checkpoint_preserves_other_drafts_and_git_index(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    for name in ('one.md', 'two.py', 'staged.txt'):
        (tmp_path / name).write_text('original\n')
    git('add', '.')
    git('commit', '-m', 'baseline')
    ws = Workspace(tmp_path)
    drafts = []
    for name in ('one.md', 'two.py'):
        file = ws.read(name)
        draft = ws.reviews.start(name, file['version'])
        drafts.append(ws.reviews.update(draft['id'], draft['version'],
                                       [dict(start=0, end=0, insert='reviewed\n')], 'Altay', 'human'))
    (tmp_path / 'staged.txt').write_text('staged agent work\n')
    git('add', 'staged.txt')
    (tmp_path / 'staged.txt').write_text('later unstaged work\n')
    index = git('write-tree')
    head = git('rev-parse', 'HEAD')
    ws.reviews.approve(drafts[0]['id'], drafts[0]['version'])
    assert git('rev-parse', 'HEAD') == head  # Approval saves; checkpoints commit.
    assert git('write-tree') == index
    assert ws.reviews.read(drafts[1]['id']) == drafts[1]
    assert (tmp_path / 'two.py').read_text() == 'original\n'
    Revisions(ws).checkpoint(['one.md'], 'Approve one file')
    assert git('show', 'HEAD:one.md') == 'reviewed\noriginal'
    assert git('show', 'HEAD:two.py') == 'original'
    assert git('show', 'HEAD:staged.txt') == 'original'
    assert git('show', ':staged.txt') == 'staged agent work'
    assert (tmp_path / 'staged.txt').read_text() == 'later unstaged work\n'
    assert Workspace(tmp_path).reviews.read(drafts[1]['id']) == drafts[1]


@pytest.mark.parametrize('mode', ['save', 'approve'])
def test_failed_write_keeps_discussions_origins_and_pending_reviews(tmp_path, mode):
    (tmp_path / 'note.txt').write_text('Unique passage.\n')
    ws = Workspace(tmp_path)
    file = ws.read('note.txt')
    thread = ws.create_thread('note.txt', 0, 14, 'Keep this discussion', 'Altay', file['version'])
    origin = ws.origins.read(thread['id'])
    draft = ws.reviews.start('note.txt', file['version'])
    draft = ws.reviews.update(draft['id'], draft['version'],
                              [dict(start=0, end=0, insert='Proposal\n')], 'Codex', 'agent')
    (tmp_path / 'note.txt').write_text('External\nUnique passage.\n')
    with pytest.raises(Problem) as error:
        if mode == 'save':
            ws.save('note.txt', 'Stale overwrite', file['version'])
        else:
            ws.reviews.approve(draft['id'], draft['version'])
    assert error.value.status == 409
    restarted = Workspace(tmp_path)
    assert restarted.read('note.txt')['content'] == 'External\nUnique passage.\n'
    assert restarted.get_thread(thread['id'])['quote'] == 'Unique passage'
    assert restarted.origins.read(thread['id']) == origin
    assert restarted.reviews.read(draft['id']) == draft
