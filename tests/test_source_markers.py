import pytest

from looking_glass.app import create_app
from looking_glass.file_operations import FileOperations
from looking_glass.source_markers import markers
from looking_glass.workspace import Problem, Workspace


@pytest.mark.parametrize('path,source,expected', [
    ('notes.md', '# TODO one\n#TODO two\n# NOTE three\n#NOTE four\n# TODOLOGY no\n', ['TODO one','TODO two','NOTE three','NOTE four']),
    ('main.py', '"#TODO string"\n"""# NOTE docstring"""\nx = "🦊" #TODO real\r\n# NOTE next\r\n', ['TODO real','NOTE next']),
    ('main.py', '# TODO before incomplete\nvalue = (', ['TODO before incomplete']),
    ('app.js', 'const x = "// TODO string"; //NOTE actual\n/* TODO block */\n/* more\n * NOTE continued\n */', ['NOTE actual','TODO block */','NOTE continued']),
    ('index.html', '<p>TODO prose</p><!-- TODO html -->', ['TODO html -->']),
    ('script.sh', 'echo "# TODO string"\n#TODO shell', ['TODO shell']),
    ('query.sql', "SELECT '-- TODO string'; -- NOTE sql", ['NOTE sql']),
])
def test_marker_comment_ranges(path, source, expected):
    found = markers(path, source)
    assert [source[m['start']:m['end']] for m in found] == expected


def track(ws, path):
    return ws.source_markers.track(path, True, ws.read(path)['version'])


def test_tracking_is_opt_in_persistent_idempotent_and_keeps_replies(tmp_path):
    file = tmp_path/'a.py'; file.write_text('#TODO one\n# NOTE two\n')
    ws = Workspace(tmp_path)
    assert ws.read('a.py')['track_source_markers'] is False
    assert ws.threads('a.py') == []
    track(ws, 'a.py')
    threads = ws.threads('a.py')
    assert [t['source_marker'] for t in threads] == ['TODO','NOTE']
    ws.reply(threads[0]['id'], 'Keep this reply', 'Reviewer')
    track(ws, 'a.py')
    restarted = Workspace(tmp_path)
    assert restarted.read('a.py')['track_source_markers'] is True
    assert [t['id'] for t in restarted.threads('a.py')] == [t['id'] for t in threads]
    assert restarted.get_thread(threads[0]['id'])['messages'][-1]['body'] == 'Keep this reply'
    with restarted.connection() as db:
        assert db.execute('SELECT count(*) FROM review_versions').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM review_origins').fetchone()[0] == 3


def test_removed_markers_auto_resolve_without_touching_manual_threads(tmp_path):
    file = tmp_path/'a.py'; before = '# TODO build widget\n#NOTE keep this\n'; file.write_text(before)
    ws = Workspace(tmp_path); track(ws, 'a.py')
    imported = ws.threads('a.py')[0]
    manual = ws.create_thread('a.py', 0, 19, 'Human feedback', 'User', ws.read('a.py')['version'])
    file.write_text('#NOTE keep this\n# TODO new task\n')
    ws.read('a.py')
    lost = ws.get_thread(imported['id'])
    assert lost['resolved'] and lost['anchor_status'] == 'needs_reattachment'
    assert ws.update_thread(imported['id'], resolved=False)['resolved']
    assert not ws.get_thread(manual['id'])['resolved']
    assert ws.origins.read(imported['id'])['content'] == before
    assert len([t for t in ws.threads('a.py') if t['source_marker'] and not t['resolved']]) == 2
    # A former comment which becomes a string must stop being an active marker.
    file.write_text('value = "#NOTE keep this"\n')
    assert all(t['resolved'] for t in ws.threads('a.py') if t['source_marker'])


def test_pause_preserves_discussions_resolution_and_file_move(tmp_path):
    file = tmp_path/'a.py'; file.write_text('#TODO finish implementation\n')
    ws = Workspace(tmp_path); track(ws, 'a.py')
    thread = ws.threads('a.py')[0]; ws.update_thread(thread['id'], resolved=True)
    ws.save('a.py', '#TODO finish implementation\n#NOTE next\n', ws.read('a.py')['version'])
    assert ws.get_thread(thread['id'])['resolved']
    operations = FileOperations(ws)
    operations.change('a.py', operations.info('a.py')['version'], 'renamed.py')
    assert ws.read('renamed.py')['track_source_markers']
    ws.source_markers.track('renamed.py', False, ws.read('renamed.py')['version'])
    file = tmp_path/'renamed.py'; file.write_text(file.read_text()+'#TODO paused\n')
    assert len(ws.threads('renamed.py')) == 2
    operations.change('renamed.py', operations.info('renamed.py')['version'], delete=True)
    assert all(t['resolved'] for t in ws.threads('renamed.py'))


def test_review_markers_import_on_approval_and_unattached_markers_resolve(tmp_path):
    (tmp_path/'a.py').write_text('#TODO old\n')
    ws = Workspace(tmp_path); track(ws, 'a.py'); thread = ws.threads('a.py')[0]
    draft = ws.reviews.start('a.py', ws.read('a.py')['version'])
    draft = ws.reviews.update(draft['id'], draft['version'], [dict(start=0,end=len(draft['content']),insert='#NOTE new\n')], 'User', 'human')
    assert not any(t['source_marker']=='NOTE' for t in ws.threads('a.py', review=draft['id']))
    ws.reviews.approve(draft['id'], draft['version'])
    threads = ws.threads('a.py')
    assert ws.get_thread(thread['id'])['resolved']
    assert len([t for t in threads if t['source_marker']=='NOTE' and not t['resolved']]) == 1
    draft = ws.reviews.start('a.py', ws.read('a.py')['version'])
    ws.reviews.update(draft['id'], draft['version'], [dict(start=0,end=len(draft['content']),insert='')], 'User', 'human')
    assert all(t['resolved'] for t in ws.threads('a.py', review=draft['id']) if t['source_marker'])
    note = next(t for t in ws.threads('a.py', review=draft['id']) if t['source_marker']=='NOTE')
    assert ws.update_thread(note['id'], resolved=False, review_id=draft['id'])['resolved']


def test_tracking_api_authentication_stale_version_and_lean_index(tmp_path):
    (tmp_path/'a.py').write_text('#TODO work\n')
    app = create_app(tmp_path); client = app.test_client(); ws = app.extensions['workspace']
    headers = {'X-Looking-Glass-Token':ws.token}
    data = dict(path='a.py', enabled=True, version=ws.read('a.py')['version'])
    assert client.post('/api/source-markers', json=data).status_code == 401
    assert client.post('/api/source-markers', headers=headers, json={**data,'version':'old'}).status_code == 409
    assert client.post('/api/source-markers', headers=headers, json={**data,'enabled':'true'}).status_code == 400
    assert client.post('/api/source-markers', headers=headers, json=data).json == {'enabled':True,'truncated':False}
    assert client.get('/api/thread-index', headers=headers).json[0]['source_marker'] == 'TODO'
    assert client.get('/api/thread-search-index', headers=headers).json[0]['source_marker'] == 'TODO'


def test_marker_sync_handles_duplicates_conservatively_and_bounds_imports(tmp_path):
    (tmp_path/'a.py').write_text('#TODO same\n#TODO same\n')
    ws = Workspace(tmp_path); track(ws, 'a.py'); ids = [t['id'] for t in ws.threads('a.py')]
    (tmp_path/'a.py').write_text('#TODO same\n')
    ws.read('a.py')
    assert all(ws.get_thread(i)['resolved'] for i in ids)
    assert len([t for t in ws.threads('a.py') if not t['resolved']]) == 1
    (tmp_path/'dense.md').write_text('#TODO task\n'*1010)
    track(ws, 'dense.md')
    assert len(ws.threads('dense.md')) == 1000
    assert ws.read('dense.md')['source_markers_truncated']
