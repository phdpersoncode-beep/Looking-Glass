"""Conservative ordinary-file reconciliation, separate from discussion reads."""
from .anchors import AnchorMapper
from .workspace import Problem


class DiscussionReconciler:
    def __init__(self, workspace):
        self.ws = workspace

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

    def refresh(self, db, path=None, enabled=True):
        if not enabled:
            return
        paths = [path] if path else [row[0] for row in db.execute('SELECT DISTINCT path FROM threads')]
        for name in paths:
            if name.startswith('looking-glass://git/'):
                continue
            try:
                content, _ = self.ws.text(name)
                self.reconcile(db, name, content)
            except Problem as error:
                if error.status in (404, 415):
                    db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE path=?", (name,))
                else:
                    raise
