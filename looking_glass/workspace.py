import hashlib
import json
import os
import secrets
import sqlite3
import stat
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from .anchors import relocate

MAX_TEXT = 8 * 1024 * 1024
EXCLUDED = {'.git', '.looking-glass', 'node_modules', '.venv', '__pycache__', '.pytest_cache'}


class Problem(Exception):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def directories(typed):
    """List the subdirectories of a directory for the workspace picker."""
    p = Path(typed or '~').expanduser().resolve()
    if not p.is_dir():
        raise Problem('Choose an existing directory.', 404)
    try:
        names = [e.name for e in os.scandir(p) if e.is_dir()]
    except PermissionError:
        raise Problem('Permission denied for this directory.', 403)
    names.sort(key=lambda n: (n.startswith('.'), n.lower()))
    return dict(path=str(p), parent=str(p.parent) if p.parent != p else None, directories=names[:2000])


class Workspace:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise Problem('Choose a directory.')
        self.lock = threading.RLock()
        self.meta = self.root / '.looking-glass'
        self.meta.mkdir(mode=0o700, exist_ok=True)
        token_file = self.meta / 'token'
        if not token_file.exists():
            try:
                with token_file.open('x') as file:
                    file.write(secrets.token_urlsafe(32))
                token_file.chmod(0o600)
            except FileExistsError:
                pass
        self.token = token_file.read_text().strip()
        self.db = self.meta / 'state.sqlite3'
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots(path TEXT PRIMARY KEY, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS threads(
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL, start INTEGER NOT NULL,
                    end INTEGER NOT NULL, quote TEXT NOT NULL, anchor_status TEXT NOT NULL DEFAULT 'attached',
                    resolved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES threads(id),
                    author TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(threads)')}
            if 'anchor_kind' not in columns:
                db.execute("ALTER TABLE threads ADD COLUMN anchor_kind TEXT NOT NULL DEFAULT 'source'")
            if 'render_anchor' not in columns:
                db.execute('ALTER TABLE threads ADD COLUMN render_anchor TEXT')

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.db, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            yield db

    def path(self, name):
        if not isinstance(name, str) or not name or '\\' in name:
            raise Problem('Invalid file path.')
        p = Path(name)
        if '..' in p.parts or any(part in EXCLUDED for part in p.parts):
            raise Problem('Path is outside the workspace.', 403)
        if p.is_absolute():
            # Files outside the workspace are keyed by their canonical absolute
            # path, so one file never has two thread histories.
            if p.is_relative_to(self.root) or Path(os.path.realpath(p)) != p:
                raise Problem('Open this file by its resolved path.', 403)
            full = p
        else:
            full = self.root / p
            # Symlinks are deliberately not editable, even when they point inside.
            for ancestor in [full, *full.parents]:
                if ancestor == self.root:
                    break
                if ancestor.is_symlink():
                    raise Problem('Symlink files and directories are not supported.', 403)
            if not full.resolve().is_relative_to(self.root):
                raise Problem('Path is outside the workspace.', 403)
        if not full.is_file():
            raise Problem('File no longer exists.', 404)
        return full

    def locate(self, typed):
        """Map a typed path to its key: relative inside the root, absolute outside."""
        if not isinstance(typed, str) or not typed.strip():
            raise Problem('Enter a file path.')
        p = Path(typed.strip()).expanduser()
        p = (p if p.is_absolute() else self.root / p).resolve()
        if not p.is_file():
            raise Problem('No file exists at this path.', 404)
        key = p.relative_to(self.root).as_posix() if p.is_relative_to(self.root) else str(p)
        self.path(key)
        return key

    def files(self):
        found = []
        for directory, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(directory)/d).is_symlink())
            for name in sorted(names):
                file = Path(directory) / name
                if not file.is_symlink() and file.is_file():
                    found.append(file.relative_to(self.root).as_posix())
                if len(found) >= 10000:
                    return found
        return sorted(found)

    def bytes(self, path):
        p = self.path(path)
        if p.stat().st_size > MAX_TEXT:
            raise Problem('Text files are limited to 8 MiB. STL files may be up to 64 MiB.', 413)
        return p.read_bytes()

    def text(self, path):
        raw = self.bytes(path)
        if b'\x00' in raw:
            raise Problem('This binary file is not a text document.', 415)
        try:
            return raw.decode('utf-8'), digest(raw)
        except UnicodeDecodeError:
            raise Problem('Text editing supports UTF-8 files only.', 415)

    def reconcile(self, db, path, content):
        row = db.execute('SELECT content FROM snapshots WHERE path=?', (path,)).fetchone()
        if row and row['content'] != content:
            for t in db.execute("SELECT * FROM threads WHERE path=? AND anchor_status='attached' AND anchor_kind='source'", (path,)).fetchall():
                mapped = relocate(row['content'], content, t['start'], t['end'])
                if mapped:
                    start, end = mapped
                    db.execute('UPDATE threads SET start=?, end=?, quote=? WHERE id=?',
                               (start, end, content[start:end], t['id']))
                else:
                    db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE id=?", (t['id'],))
        db.execute('INSERT INTO snapshots VALUES(?,?) ON CONFLICT(path) DO UPDATE SET content=excluded.content', (path, content))

    def read(self, path):
        with self.lock, self.connection() as db:
            content, version = self.text(path)
            self.reconcile(db, path, content)
            return dict(path=path, content=content, version=version)

    def save(self, path, content, version):
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_TEXT or '\x00' in content:
            raise Problem('Invalid or oversized text content.')
        with self.lock, self.connection() as db:
            p = self.path(path)
            old, current_version = self.text(path)
            if current_version != version:
                raise Problem('File changed on disk. Reload or merge before saving.', 409)
            self.reconcile(db, path, old)
            mode = stat.S_IMODE(p.stat().st_mode)
            fd, temporary = tempfile.mkstemp(dir=p.parent, prefix='.' + p.name + '.lg-')
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(content.encode('utf-8'))
                    file.flush()
                    os.fsync(file.fileno())
                os.chmod(temporary, mode)
                if digest(p.read_bytes()) != current_version:
                    raise Problem('File changed during save. Your edits have not been written.', 409)
                os.replace(temporary, p)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self.reconcile(db, path, content)
            return dict(path=path, content=content, version=digest(content.encode('utf-8')))

    def threads(self, path=None):
        with self.lock, self.connection() as db:
            paths = [path] if path else [r[0] for r in db.execute('SELECT DISTINCT path FROM threads')]
            for name in paths:
                try:
                    content, _ = self.text(name)
                    self.reconcile(db, name, content)
                except Problem as e:
                    if e.status in (404, 415):
                        db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE path=?", (name,))
                    else:
                        raise
            rows = db.execute('SELECT * FROM threads' + (' WHERE path=?' if path else '') + ' ORDER BY start,id', (path,) if path else ()).fetchall()
            result = []
            for row in rows:
                t = dict(row)
                t['render_anchor'] = json.loads(t['render_anchor']) if t['render_anchor'] else None
                t['resolved'] = bool(t['resolved'])
                t['messages'] = [dict(m) for m in db.execute('SELECT * FROM messages WHERE thread_id=? ORDER BY id', (t['id'],))]
                result.append(t)
            return result

    @staticmethod
    def message(author, body):
        if not isinstance(author, str) or not author.strip() or len(author) > 120:
            raise Problem('An author label of 1–120 characters is required.')
        if not isinstance(body, str) or not body.strip() or len(body) > 50000:
            raise Problem('A comment of 1–50,000 characters is required.')
        return author.strip(), body.strip()

    def create_thread(self, path, start, end, body, author, version):
        author, body = self.message(author, body)
        with self.lock, self.connection() as db:
            content, current = self.text(path)
            if current != version:
                raise Problem('Selection is stale. Reload the document before anchoring.', 409)
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content):
                raise Problem('Select a nonempty passage in the current document.')
            self.reconcile(db, path, content)
            cursor = db.execute('INSERT INTO threads(path,start,end,quote) VALUES(?,?,?,?)', (path,start,end,content[start:end]))
            identifier = cursor.lastrowid
            db.execute('INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)', (identifier,author,body))
        return self.get_thread(identifier)

    def get_thread(self, identifier):
        with self.connection() as db:
            t = db.execute('SELECT path FROM threads WHERE id=?', (identifier,)).fetchone()
        if not t:
            raise Problem('Thread not found.', 404)
        return next(t for t in self.threads(t['path']) if t['id'] == identifier)

    @staticmethod
    def rendered_anchor(anchor):
        if not isinstance(anchor,dict) or set(anchor) != {'quote','prefix','suffix'}:
            raise Problem('Provide a rendered quote, prefix, and suffix.')
        if any(not isinstance(value,str) for value in anchor.values()):
            raise Problem('Rendered anchor fields must be text.')
        if not anchor['quote'].strip() or len(anchor['quote']) > 50000 or any(len(anchor[key]) > 48 for key in ('prefix','suffix')):
            raise Problem('Invalid or oversized rendered passage.')
        return anchor

    def create_rendered_thread(self, path, anchor, body, author, version):
        anchor = self.rendered_anchor(anchor)
        author, body = self.message(author,body)
        with self.lock, self.connection() as db:
            if self.path(path).suffix.lower() not in ('.html','.htm'):
                raise Problem('Rendered anchors require an HTML file.')
            content, current = self.text(path)
            if current != version:
                raise Problem('Selection is stale. Reload the report before anchoring.',409)
            self.reconcile(db,path,content)
            cursor = db.execute("INSERT INTO threads(path,start,end,quote,anchor_kind,render_anchor) VALUES(?,0,0,?,'rendered',?)", (path,anchor['quote'],json.dumps(anchor)))
            identifier = cursor.lastrowid
            db.execute('INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)', (identifier,author,body))
        return self.get_thread(identifier)

    def reply(self, identifier, body, author):
        author, body = self.message(author, body)
        self.get_thread(identifier)
        with self.lock, self.connection() as db:
            db.execute('INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)', (identifier,author,body))
        return self.get_thread(identifier)

    def update_thread(self, identifier, resolved=None, start=None, end=None, version=None, render_anchor=None, render_attached=None):
        t = self.get_thread(identifier)
        with self.lock, self.connection() as db:
            if render_anchor is not None or render_attached is not None:
                if t['anchor_kind'] != 'rendered':
                    raise Problem('This thread has a source anchor.')
                _, current = self.text(t['path'])
                if current != version:
                    raise Problem('Report changed on disk. Reload before updating its anchor.',409)
            if render_anchor is not None:
                anchor = self.rendered_anchor(render_anchor)
                db.execute("UPDATE threads SET quote=?,render_anchor=?,anchor_status='attached' WHERE id=?", (anchor['quote'],json.dumps(anchor),identifier))
            if render_attached is not None:
                if type(render_attached) is not bool:
                    raise Problem('render_attached must be a boolean.')
                db.execute('UPDATE threads SET anchor_status=? WHERE id=?', ('attached' if render_attached else 'needs_reattachment',identifier))
            if resolved is not None:
                if type(resolved) is not bool:
                    raise Problem('resolved must be a boolean.')
                db.execute('UPDATE threads SET resolved=? WHERE id=?', (resolved,identifier))
            if start is not None or end is not None:
                if t['anchor_kind'] != 'source':
                    raise Problem('Select the passage in the rendered report to reattach this thread.')
                content, current = self.text(t['path'])
                if current != version:
                    raise Problem('Selection is stale.', 409)
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content):
                    raise Problem('Select a nonempty passage.')
                db.execute("UPDATE threads SET start=?,end=?,quote=?,anchor_status='attached' WHERE id=?", (start,end,content[start:end],identifier))
        return self.get_thread(identifier)

    def delete_thread(self, identifier):
        with self.lock, self.connection() as db:
            if not db.execute('SELECT id FROM threads WHERE id=?', (identifier,)).fetchone():
                raise Problem('Thread not found.', 404)
            db.execute('DELETE FROM messages WHERE thread_id=?', (identifier,))
            db.execute('DELETE FROM threads WHERE id=?', (identifier,))
        return dict(deleted=True)

    def delete_message(self, identifier, message_id):
        with self.lock, self.connection() as db:
            if not db.execute('SELECT id FROM messages WHERE id=? AND thread_id=?', (message_id,identifier)).fetchone():
                raise Problem('Comment not found.', 404)
            db.execute('DELETE FROM messages WHERE id=?', (message_id,))
            if not db.execute('SELECT id FROM messages WHERE thread_id=?', (identifier,)).fetchone():
                db.execute('DELETE FROM threads WHERE id=?', (identifier,))
        return dict(deleted=True)
