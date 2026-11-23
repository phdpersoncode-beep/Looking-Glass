from looking_glass.app import create_app
from looking_glass.workspace import Workspace


def test_legacy_tracking_stops_but_existing_discussions_keep_their_history(tmp_path):
    file = tmp_path / 'notes.md'
    original = '# TODO Existing task\n'
    file.write_text(original)
    ws = Workspace(tmp_path)
    version = ws.read('notes.md')['version']
    thread = ws.create_thread('notes.md', 2, len(original) - 1, 'TODO Existing task', 'Source comment', version)
    ws.reply(thread['id'], 'Keep this reply', 'Reviewer')
    with ws.connection() as db:
        db.execute('CREATE TABLE source_marker_files(path TEXT PRIMARY KEY, truncated INTEGER NOT NULL DEFAULT 0)')
        db.execute("INSERT INTO source_marker_files(path) VALUES('notes.md')")
        db.execute("UPDATE threads SET source_marker='TODO' WHERE id=?", (thread['id'],))

    app = create_app(tmp_path)
    ws = app.extensions['workspace']
    assert app.test_client().post('/api/source-markers', headers={'X-Looking-Glass-Token': ws.token}).status_code == 404
    file.write_text(original + '# NOTE Added externally\n')
    saved = ws.save('notes.md', file.read_text() + 'TODO Saved from Edit\n', ws.read('notes.md')['version'])
    draft = ws.reviews.start('notes.md', saved['version'])
    start = len(draft['content'])
    draft = ws.reviews.update(draft['id'], draft['version'],
                              [dict(start=start, end=start, insert='# NOTE Added in Review\n')], 'User', 'human')
    ws.reviews.approve(draft['id'], draft['version'])

    existing, = ws.threads()
    assert existing['id'] == thread['id']
    assert existing['source_marker'] == 'TODO'
    assert [m['body'] for m in existing['messages']] == ['TODO Existing task', 'Keep this reply']
    assert ws.origins.read(thread['id'])['content'] == original

    file.write_text('TODO Replacement\n')
    detached, = ws.threads()
    assert detached['anchor_status'] == 'needs_reattachment'
    assert not detached['resolved']
