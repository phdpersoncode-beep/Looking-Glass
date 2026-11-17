"""Workspace planning shared by the board and agent API."""
import json

from .workspace import Problem

STATUSES = ('backlog', 'in_progress', 'to_review', 'done')


class Tasks:
    def __init__(self, ws):
        self.ws = ws
        with ws.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS task_board_revision(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
                INSERT OR IGNORE INTO task_board_revision(id,revision) VALUES(1,0);
                CREATE TABLE IF NOT EXISTS tasks(
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'backlog', milestone INTEGER NOT NULL DEFAULT 0,
                    milestone_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                    archived INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS task_activity(
                    id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
                    changes TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE INDEX IF NOT EXISTS task_activity_card ON task_activity(card_id,id);
            ''')
            task_columns = {row['name'] for row in db.execute('PRAGMA table_info(tasks)')}
            if 'milestone_number' not in task_columns:
                db.execute('ALTER TABLE tasks ADD COLUMN milestone_number INTEGER')
            if 'parent_id' not in task_columns:
                db.execute('ALTER TABLE tasks ADD COLUMN parent_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL')
                db.execute('UPDATE tasks SET parent_id=milestone_id')
            if 'outline_position' not in task_columns:
                db.execute('ALTER TABLE tasks ADD COLUMN outline_position INTEGER NOT NULL DEFAULT 0')
                db.execute('UPDATE tasks SET outline_position=position')
            # Freeze the previously displayed creation-order numbers on upgrade.
            used = {row[0] for row in db.execute('SELECT milestone_number FROM tasks WHERE milestone=1 AND milestone_number IS NOT NULL')}
            for row in db.execute('SELECT id FROM tasks WHERE milestone=1 AND milestone_number IS NULL ORDER BY id').fetchall():
                number = self.free_number(used)
                db.execute('UPDATE tasks SET milestone_number=? WHERE id=?', (number,row['id']))
                used.add(number)
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS task_milestone_numbers ON tasks(milestone_number) WHERE milestone=1')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(task_board_revision)')}
            for name in ('next_card_id', 'next_activity_id'):
                if name not in columns:
                    db.execute(f'ALTER TABLE task_board_revision ADD COLUMN {name} INTEGER NOT NULL DEFAULT 1')
            for name, table in (('next_card_id','tasks'), ('next_activity_id','task_activity')):
                db.execute(f'UPDATE task_board_revision SET {name}=MAX({name},(SELECT COALESCE(MAX(id),0)+1 FROM {table})) WHERE id=1')

    @staticmethod
    def free_number(used):
        number = 1
        while number in used:
            number += 1
        if number > 999999:
            raise Problem('No milestone numbers are available.')
        return number

    @staticmethod
    def hierarchy(db):
        """Validate the forest and derive each descendant's milestone atomically."""
        cards = {row['id']: dict(row) for row in db.execute('SELECT * FROM tasks')}
        for card in cards.values():
            seen, current, milestone = {card['id']}, card, None
            while current['parent_id'] is not None:
                parent = cards.get(current['parent_id'])
                if parent is None or parent['id'] in seen:
                    raise Problem('A card cannot be nested inside itself or its descendants.')
                seen.add(parent['id'])
                if len(seen) > 32:
                    raise Problem('Task hierarchies support up to 32 levels.')
                if parent['milestone']:
                    milestone = parent['id']
                current = parent
            if card['milestone'] and card['parent_id'] is not None:
                raise Problem('Milestones stay at the top level; nest tasks beneath them.')
            if card['milestone_id'] != milestone:
                db.execute('UPDATE tasks SET milestone_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (milestone,card['id']))

    @staticmethod
    def reparent(db, ids, parent):
        if parent is not None:
            if type(parent) is not int or parent in ids:
                raise Problem('Invalid parent card.')
            target = db.execute('SELECT * FROM tasks WHERE id=? AND archived=0', (parent,)).fetchone()
            if not target:
                raise Problem('Choose an active parent card.')
        position = db.execute('SELECT COALESCE(MAX(outline_position),0) FROM tasks').fetchone()[0]
        for offset, identifier in enumerate(ids, 1):
            old = db.execute('SELECT parent_id FROM tasks WHERE id=?', (identifier,)).fetchone()
            if old['parent_id'] != parent:
                db.execute('UPDATE tasks SET parent_id=?,outline_position=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (parent,position+offset,identifier))

    @staticmethod
    def snapshot(db):
        cards = [dict(row) for row in db.execute('SELECT * FROM tasks ORDER BY position,id')]
        milestones = {card['id']:f"#M{card['milestone_number']}" for card in cards if card['milestone']}
        for card in cards:
            card['card_reference'] = f"#C{card['id']:02d}"
            card['milestone_reference'] = milestones.get(card['id'])
            card['reference'] = card['milestone_reference'] or card['card_reference']
        return dict(revision=db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0], cards=cards)

    def read(self, known_revision=None):
        with self.ws.connection() as db:
            db.execute('BEGIN')
            if known_revision is not None and db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0] == known_revision:
                return None
            return self.snapshot(db)

    def activity(self, identifier, *, limit=100, before=None, known_revision=None):
        if not 1 <= limit <= 1000 or (before is not None and before < 1):
            raise Problem('Use an activity limit of 1–1,000 and a positive before ID.')
        with self.ws.connection() as db:
            db.execute('BEGIN')
            if not db.execute('SELECT 1 FROM tasks WHERE id=?', (identifier,)).fetchone():
                raise Problem('Card no longer exists.', 404)
            revision = db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0]
            if revision == known_revision:
                return None
            rows = list(db.execute('SELECT * FROM task_activity WHERE card_id=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?', (identifier,before,before,limit+1)))
            return dict(revision=revision, has_older=len(rows)>limit,
                        entries=[dict(row, changes=json.loads(row['changes'])) for row in reversed(rows[:limit])])

    @staticmethod
    def add_activity(db, card_id, kind, author, body='', changes=None):
        identifier = db.execute('SELECT next_activity_id FROM task_board_revision WHERE id=1').fetchone()[0]
        db.execute('UPDATE task_board_revision SET next_activity_id=next_activity_id+1 WHERE id=1')
        db.execute('INSERT INTO task_activity(id,card_id,kind,author,body,changes) VALUES(?,?,?,?,?,?)',
                   (identifier,card_id,kind,author,body,json.dumps(changes or {},ensure_ascii=False)))

    def mutate(self, data):
        allowed = {'title', 'description', 'status', 'milestone', 'milestone_id', 'milestone_number', 'archived', 'parent_id'}
        with self.ws.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            action = data.get('action')
            author = data.get('author', 'User')
            if not isinstance(author, str) or not author.strip() or len(author) > 100:
                raise Problem('Provide an author of 1–100 characters.')
            author = author.strip()
            revision = db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0]
            if action not in ('comment', 'delete_activity') and (type(data.get('revision')) is not int or data['revision'] != revision):
                raise Problem('The board changed. Refresh and retry; your edit has been preserved.', 409)
            previous = {row['id']:dict(row) for row in db.execute('SELECT * FROM tasks')}
            if action in ('comment', 'delete_activity'):
                identifier = data.get('id')
                if type(identifier) is not int or identifier not in previous:
                    raise Problem('Card no longer exists.', 404)
                if action == 'comment':
                    body = data.get('body')
                    if not isinstance(body, str) or not body.strip() or len(body) > 100000:
                        raise Problem('Provide a comment of 1–100,000 characters.')
                    self.add_activity(db, identifier, 'comment', author, body.strip())
                else:
                    entry_id = data.get('entry_id')
                    if type(entry_id) is not int:
                        raise Problem('Provide an activity entry ID.')
                    deleted = db.execute('DELETE FROM task_activity WHERE id=? AND card_id=?', (entry_id,identifier))
                    if not deleted.rowcount:
                        raise Problem('Activity entry no longer exists.', 404)
            elif action == 'create':
                title = data.get('title')
                if not isinstance(title, str) or not title.strip() or len(title) > 500:
                    raise Problem('Provide a title of 1–500 characters.')
                status = data.get('status', 'backlog')
                if status not in STATUSES:
                    raise Problem('Invalid task status.')
                identifier = db.execute('SELECT next_card_id FROM task_board_revision WHERE id=1').fetchone()[0]
                db.execute('UPDATE task_board_revision SET next_card_id=next_card_id+1 WHERE id=1')
                db.execute('INSERT INTO tasks(id,title,status,position) VALUES(?,?,?,(SELECT COALESCE(MAX(position),0)+1 FROM tasks))', (identifier,title.strip(),status))
                db.execute('UPDATE tasks SET outline_position=(SELECT COALESCE(MAX(outline_position),0)+1 FROM tasks) WHERE id=?', (identifier,))
                if 'parent_id' in data:
                    self.reparent(db, [identifier], data['parent_id'])
                self.add_activity(db, identifier, 'update', author, 'Created card.', {'title':{'from':None,'to':title.strip()},'status':{'from':None,'to':status}})
            elif action in ('update', 'delete'):
                ids = data.get('ids')
                if not isinstance(ids, list) or not ids or len(ids) > 1000 or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
                    raise Problem('Choose 1–1,000 distinct card IDs.')
                marks = ','.join('?' for _ in ids)
                rows = list(db.execute(f'SELECT * FROM tasks WHERE id IN ({marks})', ids))
                if len(rows) != len(ids):
                    raise Problem('A selected card no longer exists.', 404)
                if action == 'delete':
                    # Lift surviving direct children to the closest surviving parent.
                    for child in previous.values():
                        if child['id'] in ids or child['parent_id'] not in ids:
                            continue
                        parent = child['parent_id']
                        while parent in ids:
                            parent = previous[parent]['parent_id']
                        db.execute('UPDATE tasks SET parent_id=? WHERE id=?', (parent,child['id']))
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
                    if 'milestone_number' in changes:
                        number = changes['milestone_number']
                        if type(number) is not int or not 1 <= number <= 999999:
                            raise Problem('Use a milestone number from 1 to 999999.')
                        if len(rows) != 1 or not changes.get('milestone', rows[0]['milestone']):
                            raise Problem('Set the number of one milestone at a time.')
                    if 'parent_id' in changes and 'milestone_id' in changes:
                        raise Problem('Set either parent_id or milestone_id, not both.')
                    parent = changes.get('milestone_id')
                    if parent is not None:
                        if type(parent) is not int or parent in ids:
                            raise Problem('Invalid milestone.')
                        target = db.execute('SELECT * FROM tasks WHERE id=? AND milestone=1 AND archived=0', (parent,)).fetchone()
                        if not target or any(changes.get('milestone', row['milestone']) for row in rows):
                            raise Problem('Assign tasks to an active milestone; milestones cannot be nested.')
                    if changes.get('milestone'):
                        changes = {**changes, 'milestone_id': None, 'parent_id': None}
                    if changes.get('milestone') is False:
                        demoted = [row['id'] for row in rows if row['milestone']]
                        for identifier in demoted:
                            db.execute('UPDATE tasks SET parent_id=NULL WHERE parent_id=?', (identifier,))
                    if 'milestone_id' in changes:
                        self.reparent(db, ids, changes['milestone_id'])
                    elif 'parent_id' in changes:
                        self.reparent(db, ids, changes['parent_id'])
                    changes = {key:value for key,value in changes.items() if key not in ('parent_id','milestone_id')}
                    used = {row['milestone_number']:row['id'] for row in db.execute('SELECT id,milestone_number FROM tasks WHERE milestone=1')}
                    for row in rows:
                        updates = dict(changes)
                        if updates.get('milestone', row['milestone']):
                            number = updates.get('milestone_number', row['milestone_number'])
                            if 'milestone_number' in updates and number in used and used[number] != row['id']:
                                raise Problem(f'Milestone #M{number} is already in use. Choose an unused number.', 409)
                            if number is None or (number in used and used[number] != row['id']):
                                number = self.free_number(used)
                            if row['milestone']:
                                used.pop(row['milestone_number'], None)
                            used[number] = row['id']
                            updates['milestone_number'] = number
                        elif row['milestone']:
                            used.pop(row['milestone_number'], None)
                        if updates:
                            db.execute(f'UPDATE tasks SET {",".join(field+"=?" for field in updates)},updated_at=CURRENT_TIMESTAMP WHERE id=?', [*updates.values(),row['id']])
                    if 'status' in changes:
                        position = db.execute('SELECT COALESCE(MAX(position),0) FROM tasks').fetchone()[0]
                        for offset, row in enumerate(rows, 1):
                            if row['status'] != changes['status']:
                                db.execute('UPDATE tasks SET position=? WHERE id=?', (position + offset, row['id']))
            elif action == 'outline_move':
                ids, parent, before = data.get('ids'), data.get('parent_id'), data.get('before')
                if not isinstance(ids,list) or not ids or len(ids)>1000 or any(type(i) is not int or i not in previous for i in ids) or len(set(ids))!=len(ids):
                    raise Problem('Choose 1–1,000 distinct existing card IDs.')
                if any(previous[i]['archived'] for i in ids):
                    raise Problem('Restore archived cards before moving them.')
                # A selected subtree travels once even if its children are selected.
                roots = []
                for identifier in ids:
                    ancestor = previous[identifier]['parent_id']
                    while ancestor is not None and ancestor not in ids:
                        ancestor = previous[ancestor]['parent_id']
                    if ancestor is None:
                        roots.append(identifier)
                self.reparent(db, roots, parent)
                order = [r[0] for r in db.execute('SELECT id FROM tasks WHERE parent_id IS ? ORDER BY outline_position,id', (parent,)) if r[0] not in roots]
                if before is not None and (type(before) is not int or before not in order):
                    raise Problem('Drop target changed. Refresh and retry.',409)
                at = order.index(before) if before is not None else len(order)
                order[at:at] = roots
                for position, identifier in enumerate(order):
                    db.execute('UPDATE tasks SET outline_position=? WHERE id=?', (position,identifier))
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
            if action not in ('comment','delete_activity'):
                self.hierarchy(db)
            # Record actual field changes, including implicit child unassignment,
            # in the same transaction as the edit. No-op saves leave no activity.
            if action not in ('comment', 'delete_activity'):
                current = {row['id']:dict(row) for row in db.execute('SELECT * FROM tasks')}
                for row in current.values():
                    old = previous.get(row['id'])
                    if old is None:
                        continue
                    changes = {key:{'from':old[key],'to':row[key]} for key in sorted(allowed) if old[key] != row[key]}
                    if action == 'outline_move' and row['id'] in data['ids']:
                        def outline_rank(cards):
                            siblings = sorted((c for c in cards.values() if c['parent_id']==row['parent_id']),key=lambda c:(c['outline_position'],c['id']))
                            return next((i+1 for i,c in enumerate(siblings) if c['id']==row['id']),None)
                        if old['parent_id']==row['parent_id'] and outline_rank(previous)!=outline_rank(current):
                            changes['outline_position'] = {'from':outline_rank(previous),'to':outline_rank(current)}
                    if action == 'move' and row['id'] == data['id'] and old['status'] == row['status']:
                        def rank(cards):
                            lane = sorted((c for c in cards.values() if c['status']==row['status'] and not c['archived']), key=lambda c:(c['position'],c['id']))
                            return [c['id'] for c in lane].index(row['id'])+1
                        old_rank, new_rank = rank(previous), rank(current)
                        if old_rank != new_rank:
                            changes['position'] = {'from':old_rank,'to':new_rank}
                    if changes:
                        self.add_activity(db, row['id'], 'update', author, changes=changes)
                for identifier in sorted(previous.keys() | current.keys()):
                    old, new = previous.get(identifier, {}), current.get(identifier, {})
                    old_parent, new_parent = old.get('milestone_id'), new.get('milestone_id')
                    if old_parent != new_parent:
                        for parent, verb in ((old_parent,'Unassigned'), (new_parent,'Assigned')):
                            if parent in current:
                                self.add_activity(db,parent,'update',author,f'{verb} #C{identifier:02d}: {new.get("title",old.get("title"))}.')
            db.execute('UPDATE task_board_revision SET revision=revision+1 WHERE id=1')
            return self.snapshot(db)
