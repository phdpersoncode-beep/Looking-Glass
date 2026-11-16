"""Opt-in TODO/NOTE discussions, derived from saved comments without evaluation."""
import io
import re
import tokenize
from pathlib import Path

from .workspace import Problem

HASH = {'.sh', '.bash', '.yaml', '.yml', '.toml', '.r', '.rb', '.pl'}
SLASH = {'.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.c', '.h', '.cpp',
         '.hpp', '.cs', '.java', '.go', '.rs', '.css', '.scss', '.swift', '.kt', '.php'}
SUPPORTED = HASH | SLASH | {'.py', '.pyi', '.md', '.markdown', '.html', '.htm', '.sql', '.lua'}
MARKER = re.compile(r'^(?:\s|[#/*<!-])*(TODO|NOTE)\b[^\r\n]*')


def markers(path, content):
    """Yield exact Unicode ranges. Python strings/docstrings are never comments."""
    suffix = Path(path).suffix.lower()
    comments = []
    if suffix in {'.py', '.pyi'}:
        lines = [0]
        lines.extend(m.end() for m in re.finditer('\n', content))
        try:
            for token in tokenize.generate_tokens(io.StringIO(content).readline):
                if token.type == tokenize.COMMENT:
                    comments.append((lines[token.start[0]-1]+token.start[1], token.string))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass  # Keep comments already parsed in an incomplete source buffer.
    elif suffix in {'.md', '.markdown'}:
        comments = [(m.start(), m.group()) for m in re.finditer(r'(?m)^[ \t]*(?:#+|<!--|//|/\*|\*)[^\r\n]*', content)]
    elif suffix in SUPPORTED:
        comment = r'\#[^\r\n]*' if suffix in HASH else r'//[^\r\n]*|/\*[\s\S]*?\*/' if suffix in SLASH else r'<!--[\s\S]*?-->' if suffix in {'.html', '.htm'} else r'--[^\r\n]*|/\*[\s\S]*?\*/'
        # Skip quoted strings before recognizing comment delimiters. Template
        # literals stay literal, including their embedded expressions.
        tokens = re.compile(r'''"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|`(?:\\[\s\S]|[^`\\])*`|(?P<comment>''' + comment + ')')
        for token in tokens.finditer(content):
            if token.group('comment'):
                offset = token.start()
                for line in token.group().splitlines(keepends=True):
                    comments.append((offset, line.rstrip('\r\n')))
                    offset += len(line)
    result = []
    for start, text in comments:
        match = MARKER.match(text)
        if match:
            end = start + len(match.group().rstrip())
            # Anchor the marker itself, without leading indentation or closing delimiters.
            start += match.start(1)
            while end > start and content[end-1] in ' \t':
                end -= 1
            result.append(dict(start=start, end=end, kind=match[1]))
    return result


class SourceMarkers:
    def __init__(self, ws):
        self.ws = ws

    def enabled(self, db, path):
        return bool(db.execute('SELECT 1 FROM source_marker_files WHERE path=?', (path,)).fetchone())

    def truncated(self, db, path):
        row = db.execute('SELECT truncated FROM source_marker_files WHERE path=?', (path,)).fetchone()
        return bool(row and row['truncated'])

    def track(self, path, enabled, version):
        if type(enabled) is not bool:
            raise Problem('enabled must be a boolean.')
        if not isinstance(path, str) or Path(path).suffix.lower() not in SUPPORTED:
            raise Problem('Choose a Markdown or supported source file.')
        with self.ws.lock, self.ws.connection() as db:
            content, current = self.ws.text(path)
            if version != current:
                raise Problem('File changed. Save or reload before tracking comments.', 409)
            self.ws.reconcile(db, path, content)
            if enabled:
                db.execute('INSERT OR IGNORE INTO source_marker_files(path) VALUES(?)', (path,))
                self.sync(db, path, content)
            else:
                db.execute('DELETE FROM source_marker_files WHERE path=?', (path,))
            return dict(enabled=enabled, truncated=self.truncated(db, path))

    def sync(self, db, path, content):
        if not self.enabled(db, path):
            return
        found = markers(path, content)
        db.execute('UPDATE source_marker_files SET truncated=? WHERE path=?', (len(found)>1000, path))
        found = found[:1000]
        rows = db.execute("SELECT * FROM threads WHERE path=? AND review_id IS NULL AND source_marker IS NOT NULL AND anchor_status='attached'", (path,)).fetchall()
        used = set()
        for thread in rows:
            match = next((i for i, marker in enumerate(found)
                          if i not in used and thread['anchor_status'] == 'attached'
                          and marker['start'] <= thread['start'] < marker['end']
                          and marker['kind'] == thread['source_marker']), None)
            if match is None:
                db.execute("UPDATE threads SET resolved=1,anchor_status='needs_reattachment' WHERE id=?", (thread['id'],))
            else:
                used.add(match)
                marker = found[match]
                db.execute('UPDATE threads SET start=?,end=?,quote=? WHERE id=?',
                           (marker['start'], marker['end'], content[marker['start']:marker['end']], thread['id']))
        template = None
        for i, marker in enumerate(found):
            if i in used:
                continue
            start, end = marker['start'], marker['end']
            quote = content[start:end]
            if template is None:
                origin = self.ws.origins.capture(db, path, content, start, end, quote)
                template = origin
            else:
                origin = db.execute('''INSERT INTO review_origins(commit_hash,git_root,git_path,snapshot_hash,start,end,quote,provenance)
                    SELECT commit_hash,git_root,git_path,snapshot_hash,?,?,?,provenance FROM review_origins WHERE id=?''',
                                    (start, end, quote, template)).lastrowid
            identifier = db.execute('INSERT INTO threads(path,start,end,quote,origin_id,source_marker) VALUES(?,?,?,?,?,?)',
                                    (path, start, end, quote, origin, marker['kind'])).lastrowid
            db.execute('INSERT INTO messages(thread_id,author,body,origin_id) VALUES(?,?,?,?)',
                       (identifier, 'Source comment', quote, origin))

    @staticmethod
    def resolve_unattached(db, path=None, review=None):
        db.execute("UPDATE threads SET resolved=1 WHERE source_marker IS NOT NULL AND anchor_status!='attached'" +
                   (' AND path=?' if path else ''), (path,) if path else ())
        if review:
            db.execute("UPDATE threads SET resolved=1 WHERE source_marker IS NOT NULL AND id IN (SELECT thread_id FROM review_anchors WHERE review_id=? AND anchor_status!='attached')", (review,))
