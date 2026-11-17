"""Workspace planning shared by the board and agent API."""
from .workspace import Problem

STATUSES = ('backlog', 'in_progress', 'to_review', 'done')


class Tasks:
    def __init__(self, ws):
        self.ws = ws
        with ws.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS task_board_revision(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO task_board_revision VALUES(1,0);
                CREATE TABLE IF NOT EXISTS tasks(
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'backlog', milestone INTEGER NOT NULL DEFAULT 0,
                    milestone_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                    archived INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')

    @staticmethod
    def snapshot(db):
        return dict(revision=db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0],
                    cards=[dict(row) for row in db.execute('SELECT * FROM tasks ORDER BY position,id')])

    def read(self, known_revision=None):
        with self.ws.connection() as db:
            db.execute('BEGIN')
            if known_revision is not None and db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0] == known_revision:
                return None
            return self.snapshot(db)

    def mutate(self, data):
        allowed = {'title', 'description', 'status', 'milestone', 'milestone_id', 'archived'}
        with self.ws.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            revision = db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0]
            if type(data.get('revision')) is not int or data['revision'] != revision:
                raise Problem('The board changed. Refresh and retry; your edit has been preserved.', 409)
            action = data.get('action')
            if action == 'create':
                title = data.get('title')
                if not isinstance(title, str) or not title.strip() or len(title) > 500:
                    raise Problem('Provide a title of 1–500 characters.')
                status = data.get('status', 'backlog')
                if status not in STATUSES:
                    raise Problem('Invalid task status.')
                db.execute('INSERT INTO tasks(title,status,position) VALUES(?,?,(SELECT COALESCE(MAX(position),0)+1 FROM tasks))', (title.strip(), status))
            elif action in ('update', 'delete'):
                ids = data.get('ids')
                if not isinstance(ids, list) or not ids or len(ids) > 1000 or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
                    raise Problem('Choose 1–1,000 distinct card IDs.')
                marks = ','.join('?' for _ in ids)
                rows = list(db.execute(f'SELECT * FROM tasks WHERE id IN ({marks})', ids))
                if len(rows) != len(ids):
                    raise Problem('A selected card no longer exists.', 404)
                if action == 'delete':
                    db.execute(f'DELETE FROM tasks WHERE id IN ({marks})', ids)
                else:
                    changes = data.get('changes')
                    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
                        raise Problem('Invalid card changes.')
                    if 'title' in changes:
                        if not isinstance(changes['title'], str) or not changes['title'].strip() or len(changes['title']) > 500:
                            raise Problem('Provide a title of 1–500 characters.')
                        changes = {**changes, 'title': changes['title'].strip()}
                    if 'description' in changes and (not isinstance(changes['description'], str) or len(changes['description']) > 100000):
                        raise Problem('Description must be text under 100,000 characters.')
                    if 'status' in changes and changes['status'] not in STATUSES:
                        raise Problem('Invalid task status.')
                    for field in ('milestone', 'archived'):
                        if field in changes and type(changes[field]) is not bool:
                            raise Problem(f'{field} must be a boolean.')
                    parent = changes.get('milestone_id')
                    if parent is not None:
                        if type(parent) is not int or parent in ids:
                            raise Problem('Invalid milestone.')
                        target = db.execute('SELECT * FROM tasks WHERE id=? AND milestone=1 AND archived=0', (parent,)).fetchone()
                        if not target or any(changes.get('milestone', row['milestone']) for row in rows):
                            raise Problem('Assign tasks to an active milestone; milestones cannot be nested.')
                    if changes.get('milestone'):
                        changes = {**changes, 'milestone_id': None}
                    if changes.get('milestone') is False:
                        db.execute(f'UPDATE tasks SET milestone_id=NULL WHERE milestone_id IN ({marks})', ids)
                    db.execute(f'UPDATE tasks SET {",".join(field+"=?" for field in changes)},updated_at=CURRENT_TIMESTAMP WHERE id IN ({marks})', [*changes.values(), *ids])
                    if 'status' in changes:
                        position = db.execute('SELECT COALESCE(MAX(position),0) FROM tasks').fetchone()[0]
                        for offset, identifier in enumerate(ids, 1):
                            db.execute('UPDATE tasks SET position=? WHERE id=?', (position + offset, identifier))
            elif action == 'move':
                identifier, before, status = data.get('id'), data.get('before'), data.get('status')
                if type(identifier) is not int or status not in STATUSES or (before is not None and type(before) is not int):
                    raise Problem('Invalid move.')
                if not db.execute('SELECT 1 FROM tasks WHERE id=? AND archived=0', (identifier,)).fetchone():
                    raise Problem('Card no longer exists.', 404)
                order = [r[0] for r in db.execute('SELECT id FROM tasks WHERE status=? AND archived=0 AND id!=? ORDER BY position,id', (status, identifier))]
                if before is not None and before not in order:
                    raise Problem('Drop target changed. Refresh and retry.', 409)
                order.insert(order.index(before) if before is not None else len(order), identifier)
                db.execute('UPDATE tasks SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, identifier))
                for position, item in enumerate(order):
                    db.execute('UPDATE tasks SET position=? WHERE id=?', (position, item))
            else:
                raise Problem('Invalid board action.')
            db.execute('UPDATE task_board_revision SET revision=revision+1 WHERE id=1')
            return self.snapshot(db)
