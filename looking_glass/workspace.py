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

from .anchors import AnchorMapper

MAX_TEXT = 8 * 1024 * 1024
MAX_BINARY = 64 * 1024 * 1024
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
        self._fingerprints = {}
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
                CREATE INDEX IF NOT EXISTS threads_path ON threads(path);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES threads(id),
                    author TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')
            db.execute('CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id)')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(threads)')}
            if 'anchor_kind' not in columns:
                db.execute("ALTER TABLE threads ADD COLUMN anchor_kind TEXT NOT NULL DEFAULT 'source'")
            if 'render_anchor' not in columns:
                db.execute('ALTER TABLE threads ADD COLUMN render_anchor TEXT')
            if 'target_ref' not in columns:
                db.execute('ALTER TABLE threads ADD COLUMN target_ref TEXT')

        from .attachments import Attachments
        self.attachments = Attachments(self)
        from .origins import Origins
        self.origins = Origins(self)
        from .reviews import Reviews
        self.reviews = Reviews(self)

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
        def scan_error(error):
            # A failed scan is not an empty workspace. Let the client retain
            # its last successful tree and report the failure.
            raise error

        for directory, dirs, names in os.walk(self.root, onerror=scan_error):
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
            raise Problem('This file is too large to open. Text and HTML files are limited to 8 MiB.', 413)
        # A writer may grow the file between stat and read. Bound the allocation.
        with p.open('rb') as file:
            raw = file.read(MAX_TEXT + 1)
        if len(raw) > MAX_TEXT:
            raise Problem('This file is too large to open. Text and HTML files are limited to 8 MiB.', 413)
        return raw

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
        if row and row['content'] == content:
            return
        if row:
            threads = db.execute("SELECT * FROM threads WHERE path=? AND review_id IS NULL AND anchor_status='attached' AND anchor_kind='source' ORDER BY id", (path,)).fetchall()
            mapper = AnchorMapper(row['content'], content) if threads else None
            for t in threads:
                # Never reinterpret stale/corrupt offsets as a different quote.
                mapped = mapper.relocate(t['start'], t['end']) if row['content'][t['start']:t['end']] == t['quote'] else None
                if mapped:
                    start, end = mapped
                    db.execute('UPDATE threads SET start=?, end=?, quote=? WHERE id=?',
                               (start, end, content[start:end], t['id']))
                else:
                    db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE id=?", (t['id'],))
        db.execute('INSERT INTO snapshots VALUES(?,?) ON CONFLICT(path) DO UPDATE SET content=excluded.content', (path, content))

    def read(self, path):
        with self.lock, self.connection() as db:
            before = self.fingerprint(path)
            content, version = self.text(path)
            self.reconcile(db, path, content)
            if before == self.fingerprint(path):
                self._fingerprints[path] = (before, version)
            return dict(path=path, content=content, version=version)

    def fingerprint(self, path):
        info = self.path(path).stat()
        return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

    def unchanged(self, path, version):
        with self.lock:
            cached = self._fingerprints.get(path)
            return bool(cached and cached[1] == version and cached[0] == self.fingerprint(path))

    def save(self, path, content, version):
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_TEXT or '\x00' in content:
            raise Problem('Invalid or oversized text content.')
        with self.lock, self.connection() as db:
            self._fingerprints.pop(path,None)
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

    def threads(self, path=None, reconcile=True, review=None):
        with self.lock, self.connection() as db:
            paths = ([path] if path else [r[0] for r in db.execute('SELECT DISTINCT path FROM threads')]) if reconcile else []
            for name in paths if reconcile else []:
                if name.startswith('looking-glass://git/'):
                    continue
                try:
                    content, _ = self.text(name)
                    self.reconcile(db, name, content)
                except Problem as e:
                    if e.status in (404, 415):
                        db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE path=?", (name,))
                    else:
                        raise
            across_reviews=bool(review and path is None)
            conditions = ["(review_id IS NULL OR review_id IN (SELECT id FROM review_drafts WHERE status='pending'))"] if across_reviews else ['(review_id IS NULL OR review_id=?)']
            parameters = [] if across_reviews else [review]
            if path:
                conditions.append('path=?'); parameters.append(path)
            rows = db.execute('SELECT * FROM threads WHERE ' + ' AND '.join(conditions) + ' ORDER BY start,id', parameters).fetchall()
            anchors = {r['thread_id']:dict(r) for r in db.execute("SELECT a.* FROM review_anchors a JOIN review_drafts d ON d.id=a.review_id WHERE d.status='pending'" if across_reviews else 'SELECT * FROM review_anchors WHERE review_id=?',() if across_reviews else (review,))} if review else {}
            messages, attachments = {}, {}
            origins = self.origins.public(db,path)
            suffix = ' WHERE thread_id IN (SELECT id FROM threads WHERE path=?)' if path else ''
            for message in db.execute('SELECT * FROM messages'+suffix+' ORDER BY id',(path,) if path else ()):
                messages.setdefault(message['thread_id'],[]).append({**dict(message), 'origin':origins.get(message['origin_id']), 'commit_hash':origins.get(message['origin_id'],{}).get('commit_hash')})
            for item in db.execute('SELECT * FROM attachments'+suffix+' ORDER BY id',(path,) if path else ()):
                attachments.setdefault(item['thread_id'],[]).append(self.attachments.public(item))
            result = []
            for row in rows:
                t = dict(row)
                if t['id'] in anchors:
                    t.update({k:anchors[t['id']][k] for k in ('start','end','quote','anchor_status')})
                    if anchors[t['id']]['render_anchor'] is not None: t['render_anchor']=anchors[t['id']]['render_anchor']
                    t['review_context'] = anchors[t['id']]['review_id']
                t['origin'] = origins.get(t['origin_id'])
                t['commit_hash'] = (t['origin'] or {}).get('commit_hash')
                t['git_target'] = (dict(kind=t['anchor_kind'],ref=t['target_ref'],commit_hash=t['commit_hash'],
                                        label=t['quote'],path=t['path'])
                                   if t['anchor_kind'] in ('commit','branch') else None)
                t['render_anchor'] = json.loads(t['render_anchor']) if t['render_anchor'] else None
                t['resolved'] = bool(t['resolved'])
                t['messages'] = messages.get(t['id'],[])
                t['attachments'] = attachments.get(t['id'],[])
                result.append(t)
            return result

    def thread_index(self, review=None):
        with self.connection() as db:
            if review:
                return [dict(row) for row in db.execute("""SELECT t.id,t.path,COALESCE(a.start,t.start) AS start,t.resolved,
                    COALESCE(a.anchor_status,t.anchor_status) AS anchor_status,t.anchor_kind,t.target_ref,t.review_id
                    FROM threads t LEFT JOIN review_anchors a ON a.thread_id=t.id AND a.review_id IN (SELECT id FROM review_drafts WHERE status='pending')
                    WHERE t.review_id IS NULL OR t.review_id IN (SELECT id FROM review_drafts WHERE status='pending') ORDER BY t.path,start,t.id""")]
            return [dict(row) for row in db.execute('SELECT id,path,start,resolved,anchor_status,anchor_kind,target_ref,review_id FROM threads WHERE review_id IS NULL ORDER BY path,start,id')]

    @staticmethod
    def message(author, body, allow_empty=False):
        if not isinstance(author, str) or not author.strip() or len(author) > 120:
            raise Problem('An author label of 1–120 characters is required.')
        if not isinstance(body, str) or (not body.strip() and not allow_empty) or len(body) > 50000:
            raise Problem('A comment of 1–50,000 characters is required.')
        return author.strip(), body.strip()

    def query_threads(self, path=None, status='all', q=None, author=None,
                      anchor_status=None, limit=50, offset=0, summary='true', review=None):
        """Shared literal, case-insensitive search with stable ID pagination."""
        if status not in ('all', 'open', 'resolved'):
            raise Problem('Status must be all, open, or resolved.')
        if anchor_status not in (None, 'attached', 'needs_reattachment'):
            raise Problem('Anchor status must be attached or needs_reattachment.')
        if summary not in ('true', 'false'):
            raise Problem('Summary must be true or false.')
        limit = self.query_integer(limit, 'Limit', 1, 1000)
        offset = self.query_integer(offset, 'Offset', 0)
        items = []
        for t in sorted(self.threads(path,review=review), key=lambda t: t['id']):
            if status != 'all' and t['resolved'] != (status == 'resolved'):
                continue
            if anchor_status and t['anchor_status'] != anchor_status:
                continue
            if author and not any(m['author'].casefold() == author.casefold() for m in t['messages']):
                continue
            if q and not any(q.casefold() in text.casefold() for text in
                             [t['quote'], *[m['body'] for m in t['messages']]]):
                continue
            items.append(t)
        total = len(items)
        page = items[offset:offset+limit]
        if summary == 'true':
            page = [dict(id=t['id'], path=t['path'], quote=t['quote'], resolved=t['resolved'],
                         anchor_status=t['anchor_status'], anchor_kind=t['anchor_kind'],
                         git_target=t['git_target'],
                         commit_hash=t['commit_hash'], origin=t['origin'], created_at=t['created_at'], message_count=len(t['messages']),
                         last_message={**t['messages'][-1], 'body':t['messages'][-1]['body'][:240]})
                    for t in page]
        return dict(threads=page, total=total, limit=limit, offset=offset,
                    next_offset=offset+limit if offset+limit < total else None)

    @staticmethod
    def query_integer(value, name, minimum, maximum=None):
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise Problem(f'{name} must be an integer.')
        if number < minimum or (maximum is not None and number > maximum):
            bounds = f'{minimum}–{maximum}' if maximum is not None else f'at least {minimum}'
            raise Problem(f'{name} must be {bounds}.')
        return number

    def thread_context(self, identifier, context_lines=10, review=None):
        context_lines = self.query_integer(context_lines, 'Context lines', 0, 100)
        with self.lock:
            t = self.get_thread(identifier,review=review)
            if t['git_target']:
                t['context'] = dict(t['git_target'],content=self.origins.read(identifier)['content'])
            elif t['anchor_kind'] == 'rendered':
                t['context'] = dict(kind='rendered', **t['render_anchor'])
            elif t['anchor_kind'] == 'review_removed':
                t['context'] = dict(kind='removed',content=self.origins.read(identifier)['content'],review_id=t.get('review_id'))
            elif t['anchor_status'] != 'attached':
                t['context'] = dict(kind='unavailable', reason='Anchor needs reattachment; source positions are unreliable.')
            else:
                if t.get('review_context') or t.get('review_id'):
                    draft = self.reviews.read(t.get('review_context') or t['review_id'])
                    content,version = draft['content'],draft['version']
                else:
                    content, version = self.text(t['path'])
                # An external writer can change the file after anchor reconciliation.
                if content[t['start']:t['end']] != t['quote']:
                    t['context'] = dict(kind='unavailable', reason='File changed while reading; read the thread again.')
                    return t
                # Count only LF boundaries, including CRLF. Unicode separators
                # inside a line must not change the editor's line numbers.
                parts = content.split('\n')
                lines = [part+'\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
                start_line = content.count('\n', 0, t['start']) + 1
                end_line = content.count('\n', 0, t['end']-1) + 1
                first = max(1, start_line-context_lines)
                last = min(len(lines), end_line+context_lines)
                t['context'] = dict(kind='source', version=version, start_line=start_line,
                                    end_line=end_line, first_line=first, last_line=last,
                                    content=''.join(lines[first-1:last]))
            return t

    def create_git_thread(self, target, body, author, allow_empty=False):
        from .revisions import Revisions
        author, body = self.message(author,body,allow_empty)
        with self.lock, self.connection() as db:
            target = Revisions(self).discussion_target(target)
            quote,content = target['label'],target['content']
            origin = self.origins.capture(db,target['path'],content,0,len(content),quote,
                metadata=dict(commit_hash=target['commit_hash'],git_root=target['git_root'],git_path=None))
            identifier = db.execute('INSERT INTO threads(path,start,end,quote,anchor_kind,target_ref,origin_id) VALUES(?,?,?,?,?,?,?)',
                (target['path'],0,len(content),quote,target['kind'],target['ref'],origin)).lastrowid
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',(identifier,author,body,origin))
        return self.get_thread(identifier)

    def create_thread(self, path, start, end, body, author, version, allow_empty=False):
        author, body = self.message(author, body, allow_empty)
        with self.lock, self.connection() as db:
            content, current = self.text(path)
            if current != version:
                raise Problem('Selection is stale. Reload the document before anchoring.', 409)
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content):
                raise Problem('Select a nonempty passage in the current document.')
            self.reconcile(db, path, content)
            cursor = db.execute('INSERT INTO threads(path,start,end,quote) VALUES(?,?,?,?)', (path,start,end,content[start:end]))
            identifier = cursor.lastrowid
            origin = self.origins.capture(db,path,content,start,end,content[start:end])
            db.execute('UPDATE threads SET origin_id=? WHERE id=?',(origin,identifier))
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)', (identifier,author,body,origin))
        return self.get_thread(identifier)

    def get_thread(self, identifier, review=None):
        with self.connection() as db:
            t = db.execute('SELECT path,review_id FROM threads WHERE id=?', (identifier,)).fetchone()
        if not t:
            raise Problem('Thread not found.', 404)
        return next(t for t in self.threads(t['path'],review=review or t['review_id']) if t['id'] == identifier)

    @staticmethod
    def rendered_anchor(anchor):
        if not isinstance(anchor,dict) or set(anchor) != {'quote','prefix','suffix'}:
            raise Problem('Provide a rendered quote, prefix, and suffix.')
        if any(not isinstance(value,str) for value in anchor.values()):
            raise Problem('Rendered anchor fields must be text.')
        if not anchor['quote'].strip() or len(anchor['quote']) > 50000 or any(len(anchor[key]) > 48 for key in ('prefix','suffix')):
            raise Problem('Invalid or oversized rendered passage.')
        return anchor

    def create_rendered_thread(self, path, anchor, body, author, version, allow_empty=False):
        anchor = self.rendered_anchor(anchor)
        author, body = self.message(author,body,allow_empty)
        with self.lock, self.connection() as db:
            if self.path(path).suffix.lower() not in ('.html','.htm'):
                raise Problem('Rendered anchors require an HTML file.')
            content, current = self.text(path)
            if current != version:
                raise Problem('Selection is stale. Reload the report before anchoring.',409)
            self.reconcile(db,path,content)
            cursor = db.execute("INSERT INTO threads(path,start,end,quote,anchor_kind,render_anchor) VALUES(?,0,0,?,'rendered',?)", (path,anchor['quote'],json.dumps(anchor)))
            identifier = cursor.lastrowid
            origin = self.origins.capture(db,path,content,0,0,anchor['quote'],anchor)
            db.execute('UPDATE threads SET origin_id=? WHERE id=?',(origin,identifier))
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)', (identifier,author,body,origin))
        return self.get_thread(identifier)

    def reply(self, identifier, body, author, allow_empty=False, review=None):
        author, body = self.message(author, body, allow_empty)
        with self.lock:
            t = self.get_thread(identifier,review=review)
            if t['git_target']:
                original = self.origins.read(identifier)
                content = original['content']
                metadata = {key:original['origin'][key] for key in ('commit_hash','git_root','git_path')}
                provenance = 'inherited'
                if t['anchor_kind'] == 'branch':
                    from .revisions import Revisions
                    try:
                        target = Revisions(self).discussion_target(dict(kind='branch',ref=t['target_ref']))
                        content = target['content']
                        metadata = dict(commit_hash=target['commit_hash'],git_root=target['git_root'],git_path=None)
                        provenance = 'captured'
                    except Problem as error:
                        if error.status != 404:
                            raise
                with self.connection() as db:
                    origin = self.origins.capture(db,t['path'],content,0,len(content),t['quote'],
                                                  provenance=provenance,metadata=metadata)
                    db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',
                               (identifier,author,body,origin))
                return self.get_thread(identifier)
            provenance='captured'
            try:
                if t['anchor_kind']=='review_removed':
                    content=self.origins.read(identifier)['content']
                elif t.get('review_id') or t.get('review_context'):
                    content = self.reviews.read(t.get('review_context') or t['review_id'])['content']
                else:
                    content, _ = self.text(t['path'])
                start,end,quote,render_anchor = t['start'],t['end'],t['quote'],t['render_anchor']
                if t['anchor_kind']=='source' and content[start:end]!=quote:
                    raise Problem('Missing passage.',404)
            except Problem as error:
                if error.status not in (404,415): raise
                provenance='inherited'
                original=self.origins.read(identifier)
                content=original['content'];origin=original['origin']
                start,end,quote,render_anchor=origin['start'],origin['end'],origin['quote'],origin['render_anchor']
            with self.connection() as db:
                origin=self.origins.capture(db,t['path'],content,start,end,quote,render_anchor,provenance=provenance,
                                            metadata=self.origins.metadata(t['path'],t['origin']))
                db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)', (identifier,author,body,origin))
        return self.get_thread(identifier)

    def edit_message(self, identifier, message_id, body):
        _,body=self.message('author',body)
        with self.lock,self.connection() as db:
            if not db.execute('SELECT 1 FROM messages WHERE id=? AND thread_id=?',(message_id,identifier)).fetchone():
                raise Problem('Comment not found.',404)
            db.execute('UPDATE messages SET body=? WHERE id=? AND thread_id=?',(body,message_id,identifier))
        return self.get_thread(identifier)

    def update_thread(self, identifier, resolved=None, start=None, end=None, version=None, render_anchor=None, render_attached=None, review_id=None):
        t = self.get_thread(identifier,review=review_id)
        review_id = review_id or t.get('review_id')
        with self.lock, self.connection() as db:
            if review_id:
                row=self.reviews.row(db,review_id)
                if row['path']!=t['path']: raise Problem('Review belongs to another file.')
                self.reviews.check(row,version) if any(x is not None for x in (start,end,render_anchor,render_attached)) else None
                content,current=row['content'],self.reviews.version(row)
                db.execute('INSERT OR IGNORE INTO review_anchors(review_id,thread_id,start,end,quote,anchor_status,render_anchor) VALUES(?,?,?,?,?,?,?)',
                           (review_id,identifier,t['start'],t['end'],t['quote'],t['anchor_status'],json.dumps(t['render_anchor']) if t['render_anchor'] else None))
            else:
                content,current=self.text(t['path']) if any(x is not None for x in (start,end,render_anchor,render_attached)) else (None,None)
            def update_anchor(fields,values):
                if review_id:
                    db.execute('UPDATE review_anchors SET '+fields+' WHERE review_id=? AND thread_id=?',(*values,review_id,identifier))
                else:
                    db.execute('UPDATE threads SET '+fields+' WHERE id=?',(*values,identifier))
            if render_anchor is not None or render_attached is not None:
                if t['anchor_kind'] != 'rendered': raise Problem('This thread has a source anchor.')
                if current != version: raise Problem('Report changed. Reload before updating its anchor.',409)
            if render_anchor is not None:
                anchor=self.rendered_anchor(render_anchor)
                update_anchor("quote=?,render_anchor=?,anchor_status='attached'",(anchor['quote'],json.dumps(anchor)))
            if render_attached is not None:
                if type(render_attached) is not bool: raise Problem('render_attached must be a boolean.')
                update_anchor('anchor_status=?',('attached' if render_attached else 'needs_reattachment',))
            if resolved is not None:
                if type(resolved) is not bool: raise Problem('resolved must be a boolean.')
                db.execute('UPDATE threads SET resolved=? WHERE id=?',(resolved,identifier))
            if start is not None or end is not None:
                if t['anchor_kind'] not in ('source','review_removed'): raise Problem('Select the passage in the rendered report to reattach this thread.')
                if current != version: raise Problem('Selection is stale.',409)
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content): raise Problem('Select a nonempty passage.')
                update_anchor("start=?,end=?,quote=?,anchor_status='attached'",(start,end,content[start:end]))
                if t['anchor_kind']=='review_removed': db.execute("UPDATE threads SET anchor_kind='source',render_anchor=NULL WHERE id=?",(identifier,))
        return self.get_thread(identifier,review=review_id)

    def delete_thread(self, identifier):
        with self.lock, self.connection() as db:
            if not db.execute('SELECT id FROM threads WHERE id=?', (identifier,)).fetchone():
                raise Problem('Thread not found.', 404)
            self._delete_attachment_files(db,identifier)
            db.execute('DELETE FROM messages WHERE thread_id=?', (identifier,))
            db.execute('DELETE FROM threads WHERE id=?', (identifier,))
            self.origins.collect(db)
        return dict(deleted=True)

    def delete_message(self, identifier, message_id):
        with self.lock, self.connection() as db:
            if not db.execute('SELECT id FROM messages WHERE id=? AND thread_id=?', (message_id,identifier)).fetchone():
                raise Problem('Comment not found.', 404)
            for item in db.execute('SELECT storage_key FROM attachments WHERE message_id=?',(message_id,)):
                (self.attachments.directory/item['storage_key']).unlink(missing_ok=True)
            db.execute('DELETE FROM messages WHERE id=?', (message_id,))
            if not db.execute('SELECT id FROM messages WHERE thread_id=?', (identifier,)).fetchone():
                self._delete_attachment_files(db,identifier)
                db.execute('DELETE FROM threads WHERE id=?', (identifier,))
            self.origins.collect(db)
        return dict(deleted=True)

    def _delete_attachment_files(self, db, identifier):
        for row in db.execute('SELECT storage_key FROM attachments WHERE thread_id=?',(identifier,)):
            (self.attachments.directory/row['storage_key']).unlink(missing_ok=True)
