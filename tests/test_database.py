"""Observable contracts for moving local project state through Git-friendly SQL."""
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from looking_glass import database
from looking_glass.workspace import Workspace


def sql_dump(root):
    output = io.StringIO()
    database.dump(root, output)
    return output.getvalue()


def cli(root, *arguments, input=None, cwd=None):
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    return subprocess.run([sys.executable, '-m', 'looking_glass.cli', 'database',
                           '--root', str(root), *arguments], input=input, text=True,
                          capture_output=True, env=environment, cwd=cwd, timeout=15)


def cli_bytes(root, *arguments, input=None, stream_encoding='cp1252'):
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]),
                       PYTHONIOENCODING=stream_encoding)
    return subprocess.run([sys.executable, '-m', 'looking_glass.cli', 'database',
                           '--root', str(root), *arguments], input=input,
                          capture_output=True, env=environment, timeout=15)


@pytest.fixture
def populated(tmp_path):
    root = tmp_path / 'machine A #? 🪞'
    root.mkdir()
    (root / 'notes.md').write_bytes('A München passage.\r\nMore text.\r\n'.encode())
    ws = Workspace(root)
    file = ws.read('notes.md')
    thread = ws.create_thread('notes.md', 0, 9, "Question 'quoted'\nsecond line\r\nNUL:\0!", 'Human', file['version'])
    ws.reply(thread['id'], 'Reply 🪞', 'Agent')
    ws.update_thread(thread['id'], resolved=True)
    draft = ws.reviews.start('notes.md', file['version'])
    draft = ws.reviews.update(draft['id'], draft['version'],
                              [dict(start=0, end=0, insert='Proposal\n')], 'Agent', 'agent')
    ws.reviews.create_thread(draft['id'], draft['version'], 0, 8, 'Draft discussion', 'Human')
    ws.attachments.add(thread['id'], io.BytesIO(b'upload bytes'), 'evidence.txt')
    image = io.BytesIO()
    Image.new('RGB', (2, 2), 'purple').save(image, 'PNG')
    image.seek(0)
    ws.images.add(image, 'figure.png')
    with ws.connection() as db:
        db.execute('INSERT INTO pdf_bookmarks VALUES(?,?,?,?)',
                   ('paper.pdf', 2, 'version', '[{"title":"Introduction","page":1}]'))
        db.execute('PRAGMA user_version=7')
    return ws


def test_cli_round_trip_between_machines_preserves_all_state_and_local_identity(populated, tmp_path):
    source = populated
    dump = cli(source.root, 'dump')
    assert dump.returncode == 0, dump.stderr
    assert dump.stdout.startswith(database.HEADER + '\n')
    assert source.token not in dump.stdout
    assert 'upload bytes' not in dump.stdout
    assert 'char(10)' in dump.stdout and 'char(13)' in dump.stdout and 'char(0)' in dump.stdout
    destination = tmp_path / 'machine B'
    destination.mkdir()
    (destination / 'notes.md').write_bytes((source.root / 'notes.md').read_bytes())
    restored = cli(destination, 'restore', '-', input=dump.stdout)
    assert restored.returncode == 0, restored.stderr
    assert json.loads(restored.stdout)['backup'] is None
    assert not (destination / '.looking-glass' / 'token').exists()
    assert sql_dump(destination) == dump.stdout

    # Reading and replying works through the app after restart, with new credentials.
    from looking_glass.app import create_app
    app = create_app(destination)
    ws = app.extensions['workspace']
    assert ws.token != source.token
    thread = ws.get_thread(1)
    assert thread['resolved'] and thread['messages'][0]['body'].endswith('NUL:\0!')
    assert ws.origins.read(1) == source.origins.read(1)
    assert ws.reviews.read(1) == source.reviews.read(1)
    assert ws.reviews.history(1) == source.reviews.history(1)
    with source.connection() as db:
        image_id = db.execute('SELECT id FROM images').fetchone()[0]
    assert ws.images.get(image_id) == source.images.get(image_id)
    headers = {'X-Looking-Glass-Token': ws.token}
    response = app.test_client().post('/api/threads/1/replies', headers=headers,
                                       json={'author': 'Machine B', 'body': 'Restored successfully'})
    assert response.status_code == 201
    assert response.json['messages'][-1]['body'] == 'Restored successfully'
    checked = cli(destination, 'check')
    assert checked.returncode == 0, checked.stderr
    result = json.loads(checked.stdout)
    assert result['ok'] and result['integrity_check'] == ['ok'] and result['foreign_key_check'] == []
    assert result['tables']['review_edits'] == 1
    assert result['warnings'] == ['1 attachment file(s) missing or size mismatched; upload bytes are not in SQL dumps.']


@pytest.mark.parametrize('stream_encoding', ['cp1252', 'ascii', 'cp1252:replace'])
def test_sql_stdout_is_utf8_independent_of_locale(populated, tmp_path, stream_encoding):
    path = tmp_path / 'snapshot.sql'
    database.dump_file(populated.root, path)
    dumped = cli_bytes(populated.root, 'dump', stream_encoding=stream_encoding)
    assert dumped.returncode == 0, dumped.stderr
    assert dumped.stdout == path.read_bytes()
    assert 'München' in dumped.stdout.decode('utf-8')


@pytest.mark.parametrize('stream_encoding', ['cp1252', 'ascii', 'cp1252:replace'])
def test_sql_stdin_and_restore_json_are_utf8_independent_of_locale(populated, tmp_path, stream_encoding):
    path = tmp_path / 'snapshot.sql'
    database.dump_file(populated.root, path)
    destination = tmp_path / 'receiving 🪞'
    destination.mkdir()
    Workspace(destination)
    restored = cli_bytes(destination, 'restore', '--force', '-', input=path.read_bytes(),
                         stream_encoding=stream_encoding)
    assert restored.returncode == 0, restored.stderr
    result = json.loads(restored.stdout.decode('utf-8'))
    assert Path(result['backup']).parent == destination / '.looking-glass'
    assert sql_dump(destination).encode('utf-8') == path.read_bytes()


def test_sql_stdin_rejects_non_utf8_without_creating_database(populated, tmp_path):
    sql = sql_dump(populated.root).encode('utf-8')
    assert b'M\xc3\xbcnchen' in sql
    invalid = sql.replace(b'M\xc3\xbcnchen', b'M\xfcnchen')
    destination = tmp_path / 'clone'
    destination.mkdir()
    restored = cli_bytes(destination, 'restore', '-', input=invalid)
    assert restored.returncode != 0
    assert b'utf-8' in restored.stderr
    assert not database.state_path(destination).exists()


def test_deterministic_dump_ignores_insertion_order_vacuum_and_has_one_line_per_row(populated):
    ws = populated
    with ws.connection() as db:
        db.execute('INSERT INTO pdf_bookmarks VALUES(?,?,?,?)', ('z.pdf', 1, 'z', '[]'))
        db.execute('INSERT INTO pdf_bookmarks VALUES(?,?,?,?)', ('a.pdf', 1, 'a', '[]'))
    first = sql_dump(ws.root)
    with ws.connection() as db:
        rows = db.execute('SELECT * FROM pdf_bookmarks').fetchall()
        db.execute('DELETE FROM pdf_bookmarks')
        for row in reversed(rows):
            db.execute('INSERT INTO pdf_bookmarks VALUES(?,?,?,?)', tuple(row))
    with closing(sqlite3.connect(ws.db)) as db:
        db.execute('VACUUM')
    assert sql_dump(ws.root) == first
    inserts = [line for line in first.splitlines() if line.startswith('INSERT INTO')]
    assert len(inserts) == sum(database.check(ws.root)['tables'].values())
    assert all(line.endswith(';') for line in inserts)


def test_dump_includes_committed_wal_and_excludes_uncommitted_writes(populated):
    ws = populated
    with closing(sqlite3.connect(ws.db)) as connection:
        connection.execute('PRAGMA wal_autocheckpoint=0')
        connection.execute("UPDATE messages SET body='committed in WAL' WHERE id=1")
        connection.commit()
        connection.execute("UPDATE messages SET body='uncommitted change' WHERE id=1")
        dumped = sql_dump(ws.root)
        assert 'committed in WAL' in dumped and 'uncommitted change' not in dumped


def test_large_multiline_text_with_literal_escape_sequences_round_trips(populated, tmp_path):
    content = ("Quoted ' text, literal \\n \\\\n \\r \\0 🪞\r\n" * 5000) + 'end\0'
    with populated.connection() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('large.txt', content))
    destination = tmp_path / 'large-clone'
    destination.mkdir()
    database.restore(destination, sql_dump(populated.root))
    with closing(database.readonly(database.state_path(destination))) as db:
        assert db.execute("SELECT content FROM snapshots WHERE path='large.txt'").fetchone()[0] == content


def test_force_restore_backs_up_wal_state_and_preserves_token_uploads_and_files(populated):
    ws = populated
    before = sql_dump(ws.root)
    ws.reply(1, 'Local unsynced reply', 'Human')
    local = sql_dump(ws.root)
    with pytest.raises(ValueError, match='--force'):
        database.restore(ws.root, before)
    assert sql_dump(ws.root) == local
    token = (ws.meta / 'token').read_bytes()
    files = {p.name: p.read_bytes() for p in ws.attachments.directory.iterdir()}
    # Keep an ordinary connection open to exercise WAL-safe replacement.
    with closing(sqlite3.connect(ws.db)) as existing:
        result = database.restore(ws.root, before, force=True)
        assert existing.execute('SELECT count(*) FROM messages').fetchone()[0] == 3
    with closing(database.readonly(Path(result['backup']))) as backup:
        assert backup.execute('SELECT body FROM messages ORDER BY id DESC LIMIT 1').fetchone()[0] == 'Local unsynced reply'
    assert sql_dump(ws.root) == before
    assert (ws.meta / 'token').read_bytes() == token
    assert {p.name: p.read_bytes() for p in ws.attachments.directory.iterdir()} == files
    assert (ws.root / 'notes.md').read_bytes().endswith(b'\r\n')


@pytest.mark.parametrize('alter', [
    lambda sql: 'not a database',
    lambda sql: sql.replace('COMMIT;', ''),
    lambda sql: sql + '\nINVALID SQL;',
    lambda sql: sql + '\nINSERT INTO messages(id,thread_id,author,body) VALUES(999,999,\'Agent\',\'orphan\');',
    lambda sql: sql + '\nATTACH DATABASE \'outside.sqlite3\' AS outside;',
    lambda sql: sql + '\nCREATE TRIGGER surprise AFTER INSERT ON messages BEGIN DELETE FROM threads; END;',
    lambda sql: sql + '\nSELECT load_extension(\'extension\');',
    lambda sql: sql + '\nCREATE VIRTUAL TABLE surprise USING fts5(body);',
])
def test_invalid_or_unsafe_sql_never_changes_existing_state(populated, alter, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sql_dump(populated.root)
    result = cli(populated.root, 'restore', '--force', '-', input=alter(before))
    assert result.returncode != 0
    assert 'Traceback' not in result.stderr
    assert sql_dump(populated.root) == before
    assert not list(populated.meta.glob('state-backup-*'))
    assert not (tmp_path / 'outside.sqlite3').exists()


def test_checks_reject_missing_foreign_keys_wrong_schema_and_corruption(tmp_path):
    root = tmp_path
    missing = cli(root, 'check')
    assert missing.returncode != 0 and not (root / '.looking-glass').exists()
    ws = Workspace(root)
    with closing(sqlite3.connect(ws.db)) as db:
        db.execute("INSERT INTO messages(thread_id,author,body) VALUES(999,'Agent','orphan')")
        db.commit()
    invalid = cli(root, 'check')
    assert invalid.returncode != 0 and 'foreign_keys' in invalid.stderr
    assert cli(root, 'dump').returncode != 0
    with closing(sqlite3.connect(ws.db)) as db:
        db.execute('DROP TABLE messages')
        db.commit()
    invalid = cli(root, 'check')
    assert invalid.returncode != 0 and 'missing messages' in invalid.stderr
    ws.db.write_bytes(b'This is not SQLite')
    invalid = cli(root, 'check')
    assert invalid.returncode != 0 and 'Traceback' not in invalid.stderr


def test_dump_file_is_atomic_protects_private_state_and_cli_infers_restored_project(populated, tmp_path):
    output = populated.root / 'looking-glass.sql'
    dumped = cli(populated.root, 'dump', '-o', str(output))
    assert dumped.returncode == 0 and dumped.stdout == ''
    assert output.read_bytes() == sql_dump(populated.root).encode()
    previous = output.read_bytes()
    protected = cli(populated.root, 'dump', '-o', str(populated.meta / 'token'))
    assert protected.returncode != 0 and 'outside .looking-glass' in protected.stderr
    with closing(sqlite3.connect(populated.db)) as db:
        db.execute("INSERT INTO messages(thread_id,author,body) VALUES(999,'Agent','orphan')")
        db.commit()
    assert cli(populated.root, 'dump', '-o', str(output)).returncode != 0
    assert output.read_bytes() == previous
    destination = tmp_path / 'clone'
    destination.mkdir()
    restored = cli(destination, 'restore', str(output))
    assert restored.returncode == 0, restored.stderr
    child = destination / 'nested'
    child.mkdir()
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    checked = subprocess.run([sys.executable, '-m', 'looking_glass.cli', 'database', 'check'],
                             cwd=child, env=environment, capture_output=True, text=True, timeout=10)
    assert checked.returncode == 0, checked.stderr


def test_server_and_directory_switch_block_restore_until_shutdown(populated, tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    process = subprocess.Popen([sys.executable, '-m', 'looking_glass.cli', 'serve', str(populated.root), '--port', str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    other = tmp_path / 'other'
    other.mkdir()
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(url, timeout=1):
                    break
            except (URLError, TimeoutError):
                assert process.poll() is None, process.stderr.read().decode()
                assert time.monotonic() < deadline
                time.sleep(.02)
        dumped = cli(populated.root, 'dump')
        assert dumped.returncode == 0, dumped.stderr
        blocked = cli(populated.root, 'restore', '--force', '-', input=dumped.stdout)
        assert blocked.returncode != 0 and 'Stop looking-glass serve' in blocked.stderr
        request = Request(url + '/api/workspace', data=json.dumps({'path': str(other)}).encode(),
                          headers={'X-Looking-Glass-Token': populated.token, 'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=5) as response:
            assert response.status == 200
        for root in (other, populated.root):
            blocked = cli(root, 'restore', '--force', '-', input=dumped.stdout)
            assert blocked.returncode != 0 and 'Stop looking-glass serve' in blocked.stderr
    finally:
        process.terminate()
        process.wait(timeout=5)
    restored = cli(other, 'restore', '--force', '-', input=dumped.stdout)
    assert restored.returncode == 0, restored.stderr


def test_multiple_server_leases_coexist_and_exclude_restores(populated):
    dumped = sql_dump(populated.root)
    with database.project_lock(populated.root, serving=True):
        with database.project_lock(populated.root, serving=True):
            result = cli(populated.root, 'restore', '--force', '-', input=dumped)
            assert result.returncode != 0 and 'Project is busy' in result.stderr
    with database.project_lock(populated.root):
        with pytest.raises(ValueError, match='Project is busy'):
            with database.project_lock(populated.root, serving=True):
                pytest.fail('A server acquired a lease during restore')


def test_legacy_schema_can_be_restored_then_upgraded_by_workspace(tmp_path):
    from looking_glass.discussion_store import DiscussionStore
    source = tmp_path / 'legacy'
    source.mkdir()
    (source / '.looking-glass').mkdir()
    DiscussionStore(database.state_path(source))
    destination = tmp_path / 'new'
    destination.mkdir()
    database.restore(destination, sql_dump(source))
    assert 'review_drafts' not in database.check(destination)['tables']
    ws = Workspace(destination)
    assert 'review_drafts' in database.check(ws.root)['tables']


def test_sql_snapshot_survives_git_clone_without_tracking_runtime_files(populated, tmp_path):
    source = populated.root
    (source / '.gitignore').write_text('.looking-glass/\n')
    snapshot = source / 'looking-glass.sql'
    database.dump_file(source, snapshot)

    def git(root, *arguments):
        return subprocess.check_output(['git', '-C', str(root), *arguments], text=True, stderr=subprocess.PIPE)

    git(source, 'init')
    git(source, 'add', '.gitignore', 'notes.md', snapshot.name)
    git(source, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'Sync state')
    destination = tmp_path / 'clone'
    git(tmp_path, 'clone', '--no-local', str(source), str(destination))
    restored = cli(destination, 'restore', str(destination / snapshot.name))
    assert restored.returncode == 0, restored.stderr
    assert sql_dump(destination) == snapshot.read_text(encoding='utf-8')
    Workspace(destination)
    assert git(destination, 'status', '--porcelain') == ''
    assert '.looking-glass' not in git(destination, 'ls-files')
