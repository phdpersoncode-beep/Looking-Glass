"""Read-only PDFs and database-owned outlines/passage anchors."""
import io
import json
import math
import uuid

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .workspace import MAX_BINARY, Problem, digest


class PDFs:
    def __init__(self, workspace):
        self.ws = workspace
        self.cache = {}
        with self.ws.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS pdf_bookmarks(
                path TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                document_version TEXT NOT NULL, bookmarks TEXT NOT NULL)''')

    def document(self, path):
        file = self.ws.path(path)
        if file.suffix.lower() != '.pdf':
            raise Problem('Choose a PDF file.')
        fingerprint = self.ws.fingerprint(path)
        cached = self.cache.get(path)
        if cached and cached[0] == fingerprint:
            return cached[1]
        if file.stat().st_size > MAX_BINARY:
            raise Problem('PDF files are limited to 64 MiB.', 413)
        with file.open('rb') as stream:
            raw = stream.read(MAX_BINARY + 1)
        if len(raw) > MAX_BINARY:
            raise Problem('PDF files are limited to 64 MiB.', 413)
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise Problem('Password-protected PDFs are not supported.', 415)
            pages = len(reader.pages)
            if not pages:
                raise Problem('This PDF has no pages.', 415)
            bookmarks = []

            def outline(items, level=0):
                if level > 32 or len(bookmarks) >= 2000:
                    return
                for item in items:
                    if isinstance(item, list):
                        outline(item, min(level + 1, 32))
                    else:
                        page = reader.get_destination_page_number(item)
                        if page is not None and 0 <= page < pages:
                            bookmarks.append(dict(id=uuid.uuid4().hex, title=str(item.title)[:500] or 'Untitled',
                                                  page=page + 1, level=level))
                    if len(bookmarks) >= 2000:
                        break

            outline(reader.outline)
            # Invalid/skipped destinations must not create gaps in the hierarchy.
            previous = -1
            for bookmark in bookmarks:
                bookmark['level'] = min(bookmark['level'], previous + 1)
                previous = bookmark['level']
            result = dict(version=digest(raw), pages=pages, bookmarks=bookmarks, reader=reader)
        except (PdfReadError, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            raise Problem('Unable to read this PDF: it is malformed or unsupported.', 415) from error
        if len(self.cache) >= 4:
            self.cache.pop(next(iter(self.cache)))
        if fingerprint == self.ws.fingerprint(path):
            self.cache[path] = (fingerprint, result)
        return result

    def read(self, path, version=None, revision=None):
        with self.ws.lock, self.ws.connection() as db:
            document = self.document(path)
            db.execute('INSERT OR IGNORE INTO pdf_bookmarks VALUES(?,0,?,?)',
                       (path, document['version'], json.dumps(document['bookmarks'])))
            self.reconcile(db, path, document['version'])
            row = db.execute('SELECT * FROM pdf_bookmarks WHERE path=?', (path,)).fetchone()
            if version == document['version'] and revision == str(row['revision']):
                return None
            return dict(path=path, content='', version=document['version'], pages=document['pages'],
                        bookmarks=json.loads(row['bookmarks']), bookmark_revision=row['revision'],
                        bookmarks_stale=row['document_version'] != document['version'])

    def save_bookmarks(self, path, bookmarks, revision, version):
        with self.ws.lock, self.ws.connection() as db:
            document = self.document(path)
            if version != document['version']:
                raise Problem('PDF changed. Reload before editing bookmarks.', 409)
            if not isinstance(bookmarks, list) or len(bookmarks) > 2000:
                raise Problem('Provide at most 2,000 bookmarks.')
            ids, previous = set(), -1
            for item in bookmarks:
                if not isinstance(item, dict) or set(item) != {'id', 'title', 'page', 'level'}:
                    raise Problem('Each bookmark needs an id, title, page, and level.')
                if (not isinstance(item['id'], str) or not 1 <= len(item['id']) <= 80 or item['id'] in ids
                    or not isinstance(item['title'], str) or not item['title'].strip() or len(item['title']) > 500
                    or type(item['page']) is not int or not 1 <= item['page'] <= document['pages']
                    or type(item['level']) is not int or not 0 <= item['level'] <= min(32, previous + 1)):
                    raise Problem('Invalid bookmark title, page, hierarchy, or duplicate id.')
                ids.add(item['id']); previous = item['level']
            if type(revision) is not int:
                raise Problem('Provide the bookmark revision.')
            cursor = db.execute('''UPDATE pdf_bookmarks SET revision=revision+1, document_version=?, bookmarks=?
                                   WHERE path=? AND revision=?''',
                                (version, json.dumps(bookmarks), path, revision))
            if cursor.rowcount != 1:
                raise Problem('Bookmarks changed elsewhere. Reload the contents before saving.', 409)
        return self.read(path)

    @staticmethod
    def reconcile(db, path, version):
        # PDF geometry is meaningful only in the exact original bytes.
        db.execute("""UPDATE threads SET anchor_status='needs_reattachment'
                      WHERE path=? AND anchor_kind='pdf' AND json_extract(render_anchor,'$.version')!=?""",
                   (path, version))

    def anchor(self, path, anchor, version):
        document = self.document(path)
        if version != document['version']:
            raise Problem('PDF changed. Reload before selecting a passage.', 409)
        if not isinstance(anchor, dict) or set(anchor) != {'page', 'quote', 'rects'}:
            raise Problem('Provide a PDF page, quote, and text rectangles.')
        if (type(anchor['page']) is not int or not 1 <= anchor['page'] <= document['pages']
            or not isinstance(anchor['quote'], str) or not anchor['quote'].strip() or len(anchor['quote']) > 50000
            or not isinstance(anchor['rects'], list) or not 1 <= len(anchor['rects']) <= 1000):
            raise Problem('Select a nonempty passage on one PDF page.')
        for rect in anchor['rects']:
            if (not isinstance(rect, list) or len(rect) != 4
                or any(type(x) not in (float, int) or not math.isfinite(x) or not 0 <= x <= 1 for x in rect)
                or rect[2] <= 0 or rect[3] <= 0 or rect[0] + rect[2] > 1.001 or rect[1] + rect[3] > 1.001):
                raise Problem('Invalid PDF text rectangle.')
        return {**anchor, 'version': version}

    def create_thread(self, path, anchor, body, author, version, allow_empty=False):
        author, body = self.ws.message(author, body, allow_empty)
        with self.ws.lock, self.ws.connection() as db:
            anchor = self.anchor(path, anchor, version)
            # A text snapshot is readable by the existing original-context UI/CLI,
            # including scanned pages where extracted text is unavailable.
            content = f"PDF page {anchor['page']}\n\n{anchor['quote']}"
            start = len(content) - len(anchor['quote'])
            origin = self.ws.origins.capture(db, path, content, start, len(content), anchor['quote'], anchor)
            identifier = db.execute("""INSERT INTO threads(path,start,end,quote,anchor_kind,render_anchor,origin_id)
                                       VALUES(?,?,?,?,'pdf',?,?)""",
                                    (path, anchor['page'], anchor['page'], anchor['quote'], json.dumps(anchor), origin)).lastrowid
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',
                       (identifier, author, body, origin))
        return self.ws.get_thread(identifier)

    def reattach(self, identifier, anchor, version):
        with self.ws.lock, self.ws.connection() as db:
            thread = db.execute('SELECT * FROM threads WHERE id=?', (identifier,)).fetchone()
            if not thread or thread['anchor_kind'] != 'pdf':
                raise Problem('PDF discussion not found.', 404)
            anchor = self.anchor(thread['path'], anchor, version)
            db.execute("UPDATE threads SET start=?,end=?,quote=?,render_anchor=?,anchor_status='attached' WHERE id=?",
                       (anchor['page'], anchor['page'], anchor['quote'], json.dumps(anchor), identifier))
        return self.ws.get_thread(identifier)
