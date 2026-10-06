"""Thread-owned files: opaque storage keys, user-editable display names."""
import secrets
from pathlib import Path
from .workspace import Problem

MAX_ATTACHMENT = 64 * 1024 * 1024
IMAGE_TYPES = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg',
               '.gif':'image/gif', '.webp':'image/webp', '.svg':'image/svg+xml'}


class Attachments:
    def __init__(self, workspace):
        self.ws = workspace
        self.directory = workspace.meta / 'attachments'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        with workspace.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS attachments(
                id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                storage_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, size INTEGER NOT NULL,
                media_type TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS attachments_thread ON attachments(thread_id);''')
            if 'message_id' not in {row['name'] for row in db.execute('PRAGMA table_info(attachments)')}:
                db.execute('ALTER TABLE attachments ADD COLUMN message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE')
            db.execute('CREATE INDEX IF NOT EXISTS attachments_message ON attachments(message_id)')

    @staticmethod
    def name(value):
        if not isinstance(value,str) or not value.strip() or len(value)>255 or value in ('.','..') or any(c in value for c in '/\\') or any(ord(c)<32 for c in value):
            raise Problem('Use a filename of 1–255 characters without slashes or control characters.')
        return value.strip()

    @staticmethod
    def public(row):
        return {k:row[k] for k in ('id','thread_id','message_id','name','size','media_type')}

    def get(self, identifier):
        with self.ws.connection() as db:
            row=db.execute('SELECT * FROM attachments WHERE id=?',(identifier,)).fetchone()
        if not row: raise Problem('Attachment not found.',404)
        return dict(row)

    def add(self, thread_id, stream, name, message_id=None):
        name=self.name(name)
        with self.ws.connection() as db:
            if not db.execute('SELECT id FROM threads WHERE id=?',(thread_id,)).fetchone():
                raise Problem('Thread not found.',404)
        key=secrets.token_hex(24);path=self.directory/key;size=0
        try:
            with path.open('xb') as output:
                while chunk := stream.read(1024*1024):
                    size+=len(chunk)
                    if size>MAX_ATTACHMENT: raise Problem('Attachments are limited to 64 MiB.',413)
                    output.write(chunk)
            with self.ws.lock, self.ws.connection() as db:
                if not db.execute('SELECT id FROM threads WHERE id=?',(thread_id,)).fetchone():
                    raise Problem('Thread not found.',404)
                if message_id is not None and not db.execute('SELECT id FROM messages WHERE id=? AND thread_id=?',(message_id,thread_id)).fetchone():
                    raise Problem('Comment not found in this thread.',404)
                cursor=db.execute('INSERT INTO attachments(thread_id,storage_key,name,size,media_type,message_id) VALUES(?,?,?,?,?,?)',
                                  (thread_id,key,name,size,IMAGE_TYPES.get(Path(name).suffix.lower(),'application/octet-stream'),message_id))
                identifier=cursor.lastrowid
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return self.public(self.get(identifier))

    def rename(self, identifier, name):
        name=self.name(name)
        with self.ws.lock, self.ws.connection() as db:
            if not db.execute('UPDATE attachments SET name=? WHERE id=?',(name,identifier)).rowcount:
                raise Problem('Attachment not found.',404)
        return self.public(self.get(identifier))

    def delete(self, identifier):
        with self.ws.lock, self.ws.connection() as db:
            row=self.get(identifier)
            db.execute('DELETE FROM attachments WHERE id=?',(identifier,))
        (self.directory/row['storage_key']).unlink(missing_ok=True)
        return dict(deleted=True)
