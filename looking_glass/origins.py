"""Immutable, deduplicated review context alongside mutable passage anchors."""
import json
import zlib
from pathlib import Path
from .workspace import Problem, digest


class Origins:
    def __init__(self, workspace):
        self.ws = workspace
        with workspace.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS review_versions(hash TEXT PRIMARY KEY, content BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS review_origins(
                    id INTEGER PRIMARY KEY, commit_hash TEXT, git_root TEXT, git_path TEXT,
                    snapshot_hash TEXT NOT NULL REFERENCES review_versions(hash),
                    start INTEGER NOT NULL, end INTEGER NOT NULL, quote TEXT NOT NULL,
                    render_anchor TEXT, provenance TEXT NOT NULL DEFAULT 'captured');
            ''')
            for table in ('threads', 'messages'):
                if 'origin_id' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN origin_id INTEGER REFERENCES review_origins(id)')
            # Upgrade legacy rows once. Their historical HEAD was never recorded;
            # retain the last known source and explicitly label it recovered.
            for thread in db.execute('SELECT * FROM threads WHERE origin_id IS NULL').fetchall():
                row = db.execute('SELECT content FROM snapshots WHERE path=?', (thread['path'],)).fetchone()
                content = row['content'] if row else thread['quote']
                start, end = thread['start'], thread['end']
                provenance = 'recovered'
                if thread['anchor_kind'] == 'source' and content[start:end] != thread['quote']:
                    content = thread['quote']; start = 0; end = len(content); provenance = 'recovered_quote'
                origin = self.capture(db, thread['path'], content, start, end, thread['quote'],
                                      json.loads(thread['render_anchor']) if thread['render_anchor'] else None,
                                      provenance=provenance)
                db.execute('UPDATE threads SET origin_id=? WHERE id=?', (origin, thread['id']))
            db.execute('UPDATE messages SET origin_id=(SELECT origin_id FROM threads WHERE threads.id=messages.thread_id) WHERE origin_id IS NULL')

    def metadata(self, path, fallback=None):
        from .revisions import Revisions
        git = Revisions(self.ws)
        file = Path(path) if Path(path).is_absolute() else self.ws.root/path
        directory = file.parent
        while not directory.is_dir() and directory != directory.parent:
            directory = directory.parent
        repository = git.git('-C', str(directory), 'rev-parse', '--show-toplevel', check=False)
        root = Path(repository.stdout.decode().strip()) if repository.returncode == 0 else None
        if root is None and fallback and fallback.get('git_root'):
            root = Path(fallback['git_root'])
        if root is None or not root.is_dir() or not file.is_relative_to(root):
            return dict(commit_hash=None, git_root=None, git_path=None)
        head = git.git('-C', str(root), 'rev-parse', '--verify', 'HEAD', check=False)
        return dict(commit_hash=head.stdout.decode().strip() if head.returncode == 0 else None,
                    git_root=str(root), git_path=file.relative_to(root).as_posix())

    def capture(self, db, path, content, start, end, quote, render_anchor=None, provenance='captured', metadata=None):
        raw = content.encode('utf-8'); version = digest(raw)
        # Only compress a version when it is first used by a discussion.
        if not db.execute('SELECT 1 FROM review_versions WHERE hash=?', (version,)).fetchone():
            db.execute('INSERT INTO review_versions VALUES(?,?)', (version, zlib.compress(raw, 3)))
        meta = metadata if metadata is not None else self.metadata(path)
        return db.execute('''INSERT INTO review_origins(commit_hash,git_root,git_path,snapshot_hash,start,end,quote,render_anchor,provenance)
                             VALUES(?,?,?,?,?,?,?,?,?)''',
                          (meta['commit_hash'],meta['git_root'],meta['git_path'],version,start,end,quote,
                           json.dumps(render_anchor) if render_anchor else None,provenance)).lastrowid

    def public(self, db, path=None):
        # Small metadata only; document copies are fetched on explicit request.
        result = {}
        query='SELECT id,commit_hash,git_root,git_path,snapshot_hash,provenance FROM review_origins'
        if path is not None:
            query+=' WHERE id IN (SELECT origin_id FROM threads WHERE path=? UNION SELECT m.origin_id FROM messages m JOIN threads t ON t.id=m.thread_id WHERE t.path=?)'
        for row in db.execute(query,(path,path) if path is not None else ()):
            item = dict(row)
            result[item['id']] = item
        return result

    def read(self, identifier, message_id=None):
        with self.ws.connection() as db:
            if message_id is None:
                row = db.execute('SELECT path,origin_id FROM threads WHERE id=?', (identifier,)).fetchone()
            else:
                row = db.execute('SELECT t.path,m.origin_id FROM threads t JOIN messages m ON m.thread_id=t.id WHERE t.id=? AND m.id=?',
                                 (identifier,message_id)).fetchone()
            if not row:
                raise Problem('Discussion context not found.',404)
            origin = db.execute('SELECT * FROM review_origins WHERE id=?', (row['origin_id'],)).fetchone()
            if not origin:
                raise Problem('This discussion has no recoverable original context.',404)
            data = dict(origin);data['render_anchor'] = json.loads(data['render_anchor']) if data['render_anchor'] else None
            version = db.execute('SELECT content FROM review_versions WHERE hash=?', (data['snapshot_hash'],)).fetchone()
            return dict(path=row['path'],content=zlib.decompress(version['content']).decode('utf-8'),origin=data)

    def collect(self, db):
        db.execute('DELETE FROM review_origins WHERE id NOT IN (SELECT origin_id FROM threads WHERE origin_id IS NOT NULL UNION SELECT origin_id FROM messages WHERE origin_id IS NOT NULL)')
        db.execute('DELETE FROM review_versions WHERE hash NOT IN (SELECT snapshot_hash FROM review_origins)')
