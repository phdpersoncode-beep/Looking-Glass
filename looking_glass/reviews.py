"""Persistent, operation-based drafts. Disk files remain untouched until approval."""
import json
from datetime import datetime, timezone

from .workspace import MAX_TEXT, Problem, digest


def accepted(segments):
    return ''.join(s['text'] for s in segments if s['kind'] != 'delete')


def compact(segments):
    result = []
    for segment in segments:
        if not segment['text']:
            continue
        if result and {k:v for k,v in result[-1].items() if k != 'text'} == {k:v for k,v in segment.items() if k != 'text'}:
            result[-1]['text'] += segment['text']
        else:
            result.append(dict(segment))
    return result


def splice(segments, start, end, insert, metadata):
    """Offsets address accepted Unicode code points; tombstones consume no offset."""
    before, middle, after = [], [], []
    position = 0
    removed_base = False
    for segment in segments:
        text, kind = segment['text'], segment['kind']
        if kind == 'delete':
            (before if position <= start else after if position >= end else middle).append(dict(segment))
            continue
        stop = position + len(text)
        if stop <= start:
            before.append(dict(segment))
        elif position >= end:
            after.append(dict(segment))
        else:
            left, right = max(0, start-position), min(len(text), end-position)
            if left:
                before.append({**segment, 'text':text[:left]})
            if right > left and kind == 'base':
                removed_base = True
                middle.append(dict(text=text[left:right], kind='delete', **metadata))
            if right < len(text):
                after.append({**segment, 'text':text[right:]})
        position = stop
    # Undo a deletion when an exact original tombstone is restored at its offset.
    if not removed_base and insert and before and before[-1]['kind'] == 'delete' and before[-1]['text'] == insert:
        before[-1] = dict(text=insert, kind='base')
        insert = ''
    addition = [dict(text=insert, kind='insert', **metadata)] if insert else []
    return compact(before + middle + addition + after)


def relocate(start, end, operations):
    """Map an attached passage through exact edits, without fuzzy document scans."""
    for op in operations:
        a, b, size = op['start'], op['end'], len(op['insert'])
        if a == b:
            if a <= start:
                start += size; end += size
            elif a < end:
                end += size
        elif b <= start:
            shift = size - (b-a); start += shift; end += shift
        elif a < end:
            if a <= start and b >= end:
                if not size:
                    return None
                start, end = a, a+size
            else:
                start = min(start, a) if a <= start else start
                end = max(a+size, end + size-(b-a)) if b < end else a+size
        if end <= start:
            return None
    return start, end


class Reviews:
    def __init__(self, workspace):
        self.ws = workspace
        with workspace.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS review_drafts(
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL, base TEXT NOT NULL,
                    base_version TEXT NOT NULL, content TEXT NOT NULL, segments TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS review_pending_path ON review_drafts(path) WHERE status='pending';
                CREATE TABLE IF NOT EXISTS review_heads(
                    id INTEGER PRIMARY KEY REFERENCES review_drafts(id), path TEXT NOT NULL,
                    revision INTEGER NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS review_edits(
                    id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES review_drafts(id),
                    revision INTEGER NOT NULL, author TEXT NOT NULL, role TEXT NOT NULL,
                    created_at TEXT NOT NULL, operations TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS review_edit_cursor ON review_edits(review_id,id);
                CREATE TABLE IF NOT EXISTS review_anchors(
                    review_id INTEGER NOT NULL REFERENCES review_drafts(id),
                    thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    start INTEGER NOT NULL, end INTEGER NOT NULL, quote TEXT NOT NULL,
                    anchor_status TEXT NOT NULL, render_anchor TEXT, PRIMARY KEY(review_id,thread_id));
            ''')
            if 'render_anchor' not in {r['name'] for r in db.execute('PRAGMA table_info(review_anchors)')}:
                db.execute('ALTER TABLE review_anchors ADD COLUMN render_anchor TEXT')
            db.execute('INSERT OR IGNORE INTO review_heads SELECT id,path,revision,status,updated_at FROM review_drafts')
            if 'review_id' not in {r['name'] for r in db.execute('PRAGMA table_info(threads)')}:
                db.execute('ALTER TABLE threads ADD COLUMN review_id INTEGER REFERENCES review_drafts(id)')

    @staticmethod
    def stamp():
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')

    def row(self, db, identifier):
        if type(identifier) is not int:
            raise Problem('A review ID is required.')
        row = db.execute('SELECT * FROM review_drafts WHERE id=?',(identifier,)).fetchone()
        if not row:
            raise Problem('Review draft not found.',404)
        return row

    @staticmethod
    def version(row):
        return f"review:{row['id']}:{row['revision']}"

    def check(self, row, version):
        if row['status'] != 'pending' or self.version(row) != version:
            raise Problem('Review changed. Refresh before editing or approving.',409)

    def public(self, row):
        return dict(id=row['id'],path=row['path'],base=row['base'],base_version=row['base_version'],
                    content=row['content'],segments=json.loads(row['segments']),revision=row['revision'],
                    version=self.version(row),status=row['status'],created_at=row['created_at'],updated_at=row['updated_at'])

    def start(self, path, version):
        with self.ws.lock:
            with self.ws.connection() as db:
                row = db.execute("SELECT * FROM review_drafts WHERE path=? AND status='pending'",(path,)).fetchone()
                if row:
                    return self.public(row)
            file = self.ws.read(path)
            if file['version'] != version:
                raise Problem('File changed. Reload before starting a review.',409)
            timestamp = self.stamp()
            segments = [dict(text=file['content'],kind='base')] if file['content'] else []
            with self.ws.connection() as db:
                identifier = db.execute('INSERT INTO review_drafts(path,base,base_version,content,segments,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                    (path,file['content'],version,file['content'],json.dumps(segments),timestamp,timestamp)).lastrowid
                db.execute("INSERT INTO review_heads VALUES(?,?,0,'pending',?)",(identifier,path,timestamp))
                db.execute("INSERT INTO review_anchors SELECT ?,id,start,end,quote,anchor_status,render_anchor FROM threads WHERE path=? AND review_id IS NULL AND anchor_kind IN ('source','rendered')",(identifier,path))
                return self.public(self.row(db,identifier))

    def read(self, identifier):
        with self.ws.connection() as db:
            return self.public(self.row(db,identifier))

    def list(self):
        with self.ws.connection() as db:
            return [dict(r,version=self.version(r)) for r in db.execute("SELECT * FROM review_heads WHERE status='pending' ORDER BY path")]

    def update(self, identifier, version, operations, author, role, minimal=False):
        author, _ = self.ws.message(author, 'edit')
        if role not in ('human','agent'):
            raise Problem('Edit role must be human or agent.')
        if not isinstance(operations,list) or not 1 <= len(operations) <= 1000:
            raise Problem('Provide 1–1000 sequential edit operations.')
        with self.ws.lock, self.ws.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.row(db,identifier); self.check(row,version)
            db.execute("INSERT OR IGNORE INTO review_anchors SELECT ?,id,start,end,quote,anchor_status,render_anchor FROM threads WHERE path=? AND review_id IS NULL AND anchor_kind IN ('source','rendered')",(identifier,row['path']))
            content, segments = row['content'], json.loads(row['segments'])
            normalized = []
            timestamp = self.stamp()
            edit = db.execute('INSERT INTO review_edits(review_id,revision,author,role,created_at,operations) VALUES(?,?,?,?,?,?)',
                (identifier,row['revision']+1,author,role,timestamp,'[]')).lastrowid
            for op in operations:
                if not isinstance(op,dict) or set(op) != {'start','end','insert'}:
                    raise Problem('Each edit needs start, end, and insert.')
                a,b,text = op['start'],op['end'],op['insert']
                if type(a) is not int or type(b) is not int or not 0 <= a <= b <= len(content) or not isinstance(text,str) or '\x00' in text:
                    raise Problem('Invalid review edit range or text.')
                if a == b and not text:
                    continue
                removed = content[a:b]
                next_content = content[:a]+text+content[b:]
                if len(next_content.encode('utf-8')) > MAX_TEXT:
                    raise Problem('Review text exceeds the 8 MiB limit.',413)
                segments = splice(segments,a,b,text,dict(author=author,role=role,at=timestamp,edit_id=edit))
                content = next_content
                normalized.append({**op,'removed':removed})
            if not normalized:
                db.execute('DELETE FROM review_edits WHERE id=?',(edit,))
                return self.public(row)
            if content == row['base']:
                segments = [dict(text=content,kind='base')] if content else []
            # Reconcile only the reviewed file's anchors using known operations.
            for anchor in db.execute('SELECT * FROM review_anchors WHERE review_id=?',(identifier,)).fetchall():
                thread=db.execute('SELECT anchor_kind,render_anchor FROM threads WHERE id=?',(anchor['thread_id'],)).fetchone()
                kind=thread['anchor_kind']
                if kind=='review_removed':
                    removed=json.loads(thread['render_anchor'])
                    exists=any(s['kind']=='delete' and s.get('edit_id')==removed['edit_id'] and s['text']==removed['text'] for s in segments)
                    db.execute('UPDATE review_anchors SET anchor_status=? WHERE review_id=? AND thread_id=?',('attached' if exists else 'needs_reattachment',identifier,anchor['thread_id']))
                if kind!='source':
                    continue
                if anchor['anchor_status'] != 'attached':
                    continue
                mapped = relocate(anchor['start'],anchor['end'],normalized)
                if mapped:
                    a,b = mapped
                    db.execute('UPDATE review_anchors SET start=?,end=?,quote=? WHERE review_id=? AND thread_id=?',
                        (a,b,content[a:b],identifier,anchor['thread_id']))
                else:
                    db.execute("UPDATE review_anchors SET anchor_status='needs_reattachment' WHERE review_id=? AND thread_id=?",(identifier,anchor['thread_id']))
            db.execute('UPDATE review_edits SET operations=? WHERE id=?',(json.dumps(normalized,ensure_ascii=False),edit))
            db.execute('UPDATE review_drafts SET content=?,segments=?,revision=revision+1,updated_at=? WHERE id=?',
                (content,json.dumps(segments,ensure_ascii=False),timestamp,identifier))
            db.execute('UPDATE review_heads SET revision=revision+1,updated_at=? WHERE id=?',(timestamp,identifier))
            updated=self.row(db,identifier)
            if minimal:
                return dict(id=identifier,version=self.version(updated),revision=updated['revision'],updated_at=timestamp,
                            edit=dict(author=author,role=role,at=timestamp,edit_id=edit))
            return self.public(updated)

    def history(self, identifier, after=0, limit=100):
        after = self.ws.query_integer(after,'After',0)
        limit = self.ws.query_integer(limit,'Limit',1,1000)
        with self.ws.connection() as db:
            self.row(db,identifier)
            rows = db.execute('SELECT * FROM review_edits WHERE review_id=? AND id>? ORDER BY id LIMIT ?', (identifier,after,limit+1)).fetchall()
            return dict(edits=[{**dict(r),'operations':json.loads(r['operations'])} for r in rows[:limit]],
                        next_after=rows[limit-1]['id'] if len(rows)>limit else None)

    def approve(self, identifier, version):
        with self.ws.lock:
            draft = self.read(identifier)
            self.check(draft,version)
            # The ordinary save path preserves permissions and checks disk races.
            try:
                saved = self.ws.save(draft['path'],draft['content'],draft['base_version'])
            except Problem as error:
                # Recover if a process stopped after the atomic disk write but
                # before promoting anchors. Never rewrite different disk bytes.
                if error.status!=409: raise
                saved=self.ws.read(draft['path'])
                if saved['content']!=draft['content']: raise error
            with self.ws.connection() as db:
                for anchor in db.execute('SELECT * FROM review_anchors WHERE review_id=?',(identifier,)).fetchall():
                    db.execute('UPDATE threads SET start=?,end=?,quote=?,anchor_status=?,render_anchor=COALESCE(?,render_anchor) WHERE id=?',
                        (anchor['start'],anchor['end'],anchor['quote'],anchor['anchor_status'],anchor['render_anchor'],anchor['thread_id']))
                db.execute('UPDATE threads SET review_id=NULL WHERE review_id=?',(identifier,))
                db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE id IN (SELECT thread_id FROM review_anchors WHERE review_id=?) AND anchor_kind='review_removed'",(identifier,))
                db.execute("UPDATE review_drafts SET status='approved',updated_at=? WHERE id=?",(self.stamp(),identifier))
                db.execute("UPDATE review_heads SET status='approved',updated_at=? WHERE id=?",(self.stamp(),identifier))
            return saved

    def create_thread(self, identifier, version, start, end, body, author, allow_empty=False):
        author,body = self.ws.message(author,body,allow_empty)
        with self.ws.lock, self.ws.connection() as db:
            row = self.row(db,identifier); self.check(row,version)
            content = row['content']
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content):
                raise Problem('Select a nonempty passage in the review draft.')
            quote = content[start:end]
            origin = self.ws.origins.capture(db,row['path'],content,start,end,quote)
            thread = db.execute('INSERT INTO threads(path,start,end,quote,origin_id,review_id) VALUES(?,?,?,?,?,?)',
                (row['path'],start,end,quote,origin,identifier)).lastrowid
            db.execute('INSERT INTO review_anchors(review_id,thread_id,start,end,quote,anchor_status) VALUES(?,?,?,?,?,?)',(identifier,thread,start,end,quote,'attached'))
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',(thread,author,body,origin))
        return self.ws.get_thread(thread,review=identifier)

    def create_removed_thread(self, identifier, version, anchor, body, author, allow_empty=False):
        author,body = self.ws.message(author,body,allow_empty)
        if not isinstance(anchor,dict) or set(anchor) != {'edit_id','text','start','end'}:
            raise Problem('Select a removed passage again.')
        with self.ws.lock, self.ws.connection() as db:
            row=self.row(db,identifier); self.check(row,version)
            segment=next((s for s in json.loads(row['segments']) if s['kind']=='delete' and s.get('edit_id')==anchor['edit_id'] and s['text']==anchor['text']),None)
            a,b=anchor['start'],anchor['end']
            if not segment or type(a) is not int or type(b) is not int or not 0<=a<b<=len(segment['text']):
                raise Problem('Removed passage changed. Select it again.',409)
            quote=segment['text'][a:b]
            origin=self.ws.origins.capture(db,row['path'],segment['text'],a,b,quote)
            thread=db.execute("INSERT INTO threads(path,start,end,quote,origin_id,review_id,anchor_kind,render_anchor) VALUES(?,?,?,?,?,?,'review_removed',?)",
                (row['path'],a,b,quote,origin,identifier,json.dumps(anchor))).lastrowid
            db.execute('INSERT INTO review_anchors(review_id,thread_id,start,end,quote,anchor_status) VALUES(?,?,?,?,?,?)',(identifier,thread,a,b,quote,'attached'))
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',(thread,author,body,origin))
        return self.ws.get_thread(thread,review=identifier)

    def create_rendered_thread(self, identifier, version, anchor, body, author, allow_empty=False):
        anchor=self.ws.rendered_anchor(anchor)
        author,body=self.ws.message(author,body,allow_empty)
        with self.ws.lock,self.ws.connection() as db:
            row=self.row(db,identifier);self.check(row,version)
            if not row['path'].lower().endswith(('.html','.htm')):
                raise Problem('Rendered anchors require HTML.')
            origin=self.ws.origins.capture(db,row['path'],row['content'],0,0,anchor['quote'],anchor)
            thread=db.execute("INSERT INTO threads(path,start,end,quote,origin_id,review_id,anchor_kind,render_anchor) VALUES(?,0,0,?,?,?,'rendered',?)",
                (row['path'],anchor['quote'],origin,identifier,json.dumps(anchor))).lastrowid
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',(thread,author,body,origin))
        return self.ws.get_thread(thread,review=identifier)
