"""Workspace planning shared by the board and agent API."""
import json
import re
from collections import defaultdict

from .attachments import MAX_ATTACHMENT
from .workspace import Problem

STATUSES = ('backlog', 'in_progress', 'to_review', 'done')


def is_row_id(value):
    return type(value) is int and 1 <= value < 2**63


class Tasks:
    def __init__(self, ws):
        self.ws = ws
        with ws.connection() as db:
            db.executescript('''
                BEGIN IMMEDIATE;
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
                CREATE TABLE IF NOT EXISTS task_activity_attachments(
                    id INTEGER PRIMARY KEY,
                    entry_id INTEGER NOT NULL REFERENCES task_activity(id) ON DELETE CASCADE,
                    storage_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL, size INTEGER NOT NULL, media_type TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS task_activity_attachment_entry ON task_activity_attachments(entry_id);
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
            if not is_row_id(parent) or parent in ids:
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
        if not is_row_id(identifier):
            raise Problem('Card no longer exists.', 404)
        with self.ws.connection() as db:
            db.execute('BEGIN')
            if not db.execute('SELECT 1 FROM tasks WHERE id=?', (identifier,)).fetchone():
                raise Problem('Card no longer exists.', 404)
            revision = db.execute('SELECT revision FROM task_board_revision WHERE id=1').fetchone()[0]
            if revision == known_revision:
                return None
            query = 'SELECT * FROM task_activity WHERE card_id=?'
            params = [identifier]
            if before is not None and before < 2**63:
                query += ' AND id<?'
                params.append(before)
            rows = list(db.execute(query + ' ORDER BY id DESC LIMIT ?', [*params, limit+1]))
            entries = [dict(row, changes=json.loads(row['changes'])) for row in reversed(rows[:limit])]
            comments = [entry['id'] for entry in entries if entry['kind'] == 'comment']
            attachments = defaultdict(list)
            if comments:
                marks = ','.join('?' for _ in comments)
                for item in db.execute(f'SELECT id,entry_id,name,size,media_type FROM task_activity_attachments '
                                       f'WHERE entry_id IN ({marks}) ORDER BY id', comments):
                    attachments[item['entry_id']].append(dict(item))
                for entry in entries:
                    if entry['id'] in attachments:
                        entry['attachments'] = attachments[entry['id']]
            return dict(revision=revision, has_older=len(rows)>limit, entries=entries)

    def attachment(self, entry_id, identifier):
        if not is_row_id(entry_id) or not is_row_id(identifier):
            raise Problem('Attachment not found.', 404)
        with self.ws.connection() as db:
            item = db.execute('SELECT * FROM task_activity_attachments WHERE entry_id=? AND id=?',
                              (entry_id, identifier)).fetchone()
        if not item or not re.fullmatch(r'[0-9a-f]{48}', item['storage_key']):
            raise Problem('Attachment not found.', 404)
        return dict(item)

    def comment_with_attachments(self, data, uploads):
        if data.get('action') != 'comment':
            raise Problem('Attachments belong to task comments.')
        attachments, size = [], 0
        try:
            for upload in uploads:
                item = self.ws.attachments.store(upload.stream, upload.filename)
                attachments.append(item)
                size += item[2]
                if size > MAX_ATTACHMENT:
                    raise Problem('Attachments in one comment are limited to 64 MiB.', 413)
            return self.mutate(data, attachments)
        except BaseException:
            for key, *_ in attachments:
                (self.ws.attachments.directory / key).unlink(missing_ok=True)
            raise

    @staticmethod
    def add_activity(db, card_id, kind, author, body='', changes=None):
        identifier = db.execute('SELECT next_activity_id FROM task_board_revision WHERE id=1').fetchone()[0]
        db.execute('UPDATE task_board_revision SET next_activity_id=next_activity_id+1 WHERE id=1')
        db.execute('INSERT INTO task_activity(id,card_id,kind,author,body,changes) VALUES(?,?,?,?,?,?)',
                   (identifier,card_id,kind,author,body,json.dumps(changes or {},ensure_ascii=False)))
        return identifier

    @staticmethod
    def lane_order(db, status, include_milestones=False):
        return [row[0] for row in db.execute(
            'SELECT id FROM tasks WHERE status=? AND archived=0 AND (milestone=0 OR ?) ORDER BY position,id',
            (status, include_milestones))]

    @staticmethod
    def place_in_lane(db, status, ids, before, include_milestones=False):
        moving = set(ids)
        order = [identifier for identifier in Tasks.lane_order(db, status, include_milestones) if identifier not in moving]
        if before is not None and (not is_row_id(before) or before not in order):
            raise Problem('Drop target changed. Refresh and retry.', 409)
        at = order.index(before) if before is not None else len(order)
        order[at:at] = ids
        db.executemany('UPDATE tasks SET position=? WHERE id=?', enumerate(order))
        return order

    @staticmethod
    def renumber_milestones(db):
        updates = [(number, card['id']) for number, card in enumerate(db.execute(
            'SELECT id,milestone_number FROM tasks WHERE milestone=1 ORDER BY milestone_number'), 1)
            if number != card['milestone_number']]
        # The unique index must allow every freed slot to be reused.
        db.executemany('UPDATE tasks SET milestone_number=NULL WHERE id=?',
                       ((identifier,) for _, identifier in updates))
        db.executemany('UPDATE tasks SET milestone_number=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', updates)

    @staticmethod
    def outline_ranks(cards, parent):
        siblings = sorted((card for card in cards.values() if card['parent_id'] == parent),
                          key=lambda card: (card['outline_position'], card['id']))
        return {card['id']: rank for rank, card in enumerate(siblings, 1)}

    @staticmethod
    def reorder_milestone(db, identifier, before):
        milestones = db.execute('SELECT id,milestone_number FROM tasks WHERE milestone=1 AND archived=0 ORDER BY milestone_number').fetchall()
        order = [card['id'] for card in milestones]
        if not is_row_id(identifier) or identifier not in order:
            raise Problem('Choose an active milestone to reorder.')
        order.remove(identifier)
        if before is not None and (not is_row_id(before) or before not in order):
            raise Problem('Choose another active milestone as the drop target.')
        order.insert(order.index(before) if before is not None else len(order), identifier)
        updates = [(slot['milestone_number'], card_id) for slot, card_id in zip(milestones, order)
                   if slot['id'] != card_id]
        # Release the occupied numbers together so swaps satisfy the unique index.
        db.executemany('UPDATE tasks SET milestone_number=NULL WHERE id=?',
                       ((card_id,) for _, card_id in updates))
        db.executemany('UPDATE tasks SET milestone_number=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', updates)
        return bool(updates)

    def mutate(self, data, attachments=()):
        removed = []
        result = self._mutate(data, attachments, removed)
        for key in removed:
            if re.fullmatch(r'[0-9a-f]{48}', key):
                (self.ws.attachments.directory / key).unlink(missing_ok=True)
        return result

    def _mutate(self, data, attachments, removed):
        allowed = {'title', 'description', 'status', 'milestone', 'milestone_id', 'archived', 'parent_id'}
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
            if action in ('comment', 'delete_activity'):
                identifier = data.get('id')
                if (not is_row_id(identifier)
                        or not db.execute('SELECT 1 FROM tasks WHERE id=?', (identifier,)).fetchone()):
                    raise Problem('Card no longer exists.', 404)
                if action == 'comment':
                    body = data.get('body', '')
                    if not isinstance(body, str) or len(body) > 100000 or (not body.strip() and not attachments):
                        raise Problem('Provide a comment of 1–100,000 characters or attach a file.')
                    entry_id = self.add_activity(db, identifier, 'comment', author, body.strip())
                    db.executemany('INSERT INTO task_activity_attachments(entry_id,storage_key,name,size,media_type) '
                                   'VALUES(?,?,?,?,?)', ((entry_id, *item) for item in attachments))
                else:
                    entry_id = data.get('entry_id')
                    if not is_row_id(entry_id):
                        raise Problem('Provide an activity entry ID.')
                    removed.extend(row[0] for row in db.execute(
                        'SELECT storage_key FROM task_activity_attachments JOIN task_activity '
                        'ON task_activity.id=entry_id WHERE entry_id=? AND card_id=?', (entry_id, identifier)))
                    deleted = db.execute('DELETE FROM task_activity WHERE id=? AND card_id=?', (entry_id,identifier))
                    if not deleted.rowcount:
                        raise Problem('Activity entry no longer exists.', 404)
                db.execute('UPDATE task_board_revision SET revision=revision+1 WHERE id=1')
                return self.snapshot(db)

            previous = {row['id']:dict(row) for row in db.execute('SELECT * FROM tasks')}
            if action == 'create':
                title = data.get('title')
                if not isinstance(title, str) or not title.strip() or len(title) > 500:
                    raise Problem('Provide a title of 1–500 characters.')
                status = data.get('status', 'backlog')
                if status not in STATUSES:
                    raise Problem('Invalid task status.')
                milestone = data.get('milestone', False)
                if type(milestone) is not bool or (milestone and data.get('parent_id') is not None):
                    raise Problem('Milestones must stay at the top level.')
                identifier = db.execute('SELECT next_card_id FROM task_board_revision WHERE id=1').fetchone()[0]
                db.execute('UPDATE task_board_revision SET next_card_id=next_card_id+1 WHERE id=1')
                db.execute('INSERT INTO tasks(id,title,status,position) VALUES(?,?,?,(SELECT COALESCE(MAX(position),0)+1 FROM tasks))', (identifier,title.strip(),status))
                db.execute('UPDATE tasks SET outline_position=(SELECT COALESCE(MAX(outline_position),0)+1 FROM tasks) WHERE id=?', (identifier,))
                changes = {'title': {'from': None, 'to': title.strip()}, 'status': {'from': None, 'to': status}}
                if milestone:
                    used = {card['milestone_number'] for card in previous.values() if card['milestone']}
                    number = max((card['milestone_number'] for card in previous.values()
                                  if card['milestone'] and not card['archived']), default=0) + 1
                    while number in used:
                        number += 1
                    if number > 999999:
                        number = self.free_number(used)
                    db.execute('UPDATE tasks SET milestone=1,milestone_number=? WHERE id=?', (number, identifier))
                    self.reorder_milestone(db, identifier, data.get('before'))
                    number = db.execute('SELECT milestone_number FROM tasks WHERE id=?', (identifier,)).fetchone()[0]
                    changes.update(milestone={'from': False, 'to': True}, milestone_number={'from': None, 'to': number})
                else:
                    if 'parent_id' in data:
                        self.reparent(db, [identifier], data['parent_id'])
                    if data.get('before') is not None:
                        self.place_in_lane(db, status, [identifier], data['before'])
                self.add_activity(db, identifier, 'update', author, 'Created card.', changes)
            elif action == 'archive_done':
                ids = data.get('ids')
                if not isinstance(ids, list) or not ids or any(not is_row_id(i) or i not in previous
                        or previous[i]['status'] != 'done' or previous[i]['archived'] or previous[i]['milestone'] for i in ids):
                    raise Problem('Choose active tasks from the Done column.')
                if len(set(ids)) != len(ids):
                    raise Problem('Choose distinct task IDs.')
                db.executemany('UPDATE tasks SET archived=1,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                               ((identifier,) for identifier in ids))
            elif action in ('update', 'delete'):
                ids = data.get('ids')
                if not isinstance(ids, list) or not ids or len(ids) > 1000 or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
                    raise Problem('Choose 1–1,000 distinct card IDs.')
                marks = ','.join('?' for _ in ids)
                rows = [previous[identifier] for identifier in sorted(ids) if identifier in previous]
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
                    removed.extend(row[0] for row in db.execute(
                        'SELECT storage_key FROM task_activity_attachments JOIN task_activity '
                        f'ON task_activity.id=entry_id WHERE card_id IN ({marks})', ids))
                    db.execute(f'DELETE FROM tasks WHERE id IN ({marks})', ids)
                    if any(row['milestone'] for row in rows):
                        self.renumber_milestones(db)
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
                    if 'parent_id' in changes and 'milestone_id' in changes:
                        raise Problem('Set either parent_id or milestone_id, not both.')
                    parent = changes.get('milestone_id')
                    if parent is not None:
                        if not is_row_id(parent) or parent in ids:
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
                            number = row['milestone_number']
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
            elif action == 'milestone_move':
                if not self.reorder_milestone(db, data.get('id'), data.get('before')):
                    return self.snapshot(db)
            elif action == 'outline_move':
                ids, parent, before = data.get('ids'), data.get('parent_id'), data.get('before')
                if not isinstance(ids,list) or not ids or len(ids)>1000 or any(type(i) is not int or i not in previous for i in ids) or len(set(ids))!=len(ids):
                    raise Problem('Choose 1–1,000 distinct existing card IDs.')
                if any(previous[i]['archived'] for i in ids):
                    raise Problem('Restore archived cards before moving them.')
                # A selected subtree travels once even if its children are selected.
                selected = set(ids)
                roots = []
                for identifier in ids:
                    ancestor = previous[identifier]['parent_id']
                    while ancestor is not None and ancestor not in selected:
                        ancestor = previous[ancestor]['parent_id']
                    if ancestor is None:
                        roots.append(identifier)
                self.reparent(db, roots, parent)
                moving = set(roots)
                order = [r[0] for r in db.execute('SELECT id FROM tasks WHERE parent_id IS ? ORDER BY outline_position,id', (parent,)) if r[0] not in moving]
                if before is not None and (type(before) is not int or before not in order):
                    raise Problem('Drop target changed. Refresh and retry.',409)
                at = order.index(before) if before is not None else len(order)
                order[at:at] = roots
                for position, identifier in enumerate(order):
                    db.execute('UPDATE tasks SET outline_position=? WHERE id=?', (position,identifier))
            elif action == 'move':
                legacy_move = 'ids' not in data
                ids = data.get('ids', [data.get('id')])
                before, status = data.get('before'), data.get('status')
                if (not isinstance(ids, list) or not ids or len(ids) > 1000
                        or any(not is_row_id(identifier) for identifier in ids) or len(set(ids)) != len(ids)
                        or status not in STATUSES or (before is not None and not is_row_id(before))):
                    raise Problem('Invalid move.')
                if any(identifier not in previous or previous[identifier]['archived']
                       or (previous[identifier]['milestone'] and not legacy_move) for identifier in ids):
                    raise Problem('Choose active tasks to move.', 404)
                old_lane = self.lane_order(db, status, legacy_move)
                db.executemany('UPDATE tasks SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                               ((status, identifier) for identifier in ids))
                order = self.place_in_lane(db, status, ids, before, legacy_move)
            elif action == 'board_order':
                ids = data.get('ids')
                expected = {card['id'] for card in previous.values() if not card['milestone']}
                if (not isinstance(ids, list) or len(ids) != len(expected)
                        or any(not is_row_id(identifier) for identifier in ids) or set(ids) != expected):
                    raise Problem('Provide the complete task order.')
                db.executemany('UPDATE tasks SET position=? WHERE id=?', enumerate(ids))
            else:
                raise Problem('Invalid board action.')
            self.hierarchy(db)
            # Record actual field changes, including implicit child unassignment,
            # in the same transaction as the edit. No-op saves leave no activity.
            current = {row['id']:dict(row) for row in db.execute('SELECT * FROM tasks')}
            order_changes = {}
            if action == 'outline_move':
                old_ranks = self.outline_ranks(previous, parent)
                for rank, identifier in enumerate(order, 1):
                    if identifier in moving and identifier in old_ranks and old_ranks[identifier] != rank:
                        order_changes[identifier] = {'outline_position': {'from': old_ranks[identifier], 'to': rank}}
            elif action in ('move', 'board_order'):
                if action == 'move':
                    old_ranks = {identifier: rank for rank, identifier in enumerate(old_lane, 1)}
                    new_ranks = {identifier: rank for rank, identifier in enumerate(order, 1)}
                else:
                    def ranks(cards):
                        counts, result = {}, {}
                        for card in sorted(cards.values(), key=lambda card: (card['position'], card['id'])):
                            if not card['milestone']:
                                lane = card['status'], card['archived']
                                counts[lane] = counts.get(lane, 0) + 1
                                result[card['id']] = counts[lane]
                        return result

                    old_ranks, new_ranks = ranks(previous), ranks(current)
                for identifier in ids:
                    if identifier in old_ranks and old_ranks[identifier] != new_ranks[identifier]:
                        order_changes[identifier] = {'position': {'from': old_ranks[identifier], 'to': new_ranks[identifier]}}
            fields = sorted(allowed | {'milestone_number'})
            for identifier, row in current.items():
                old = previous.get(identifier)
                if old is None:
                    continue
                changes = {key: {'from': old[key], 'to': row[key]} for key in fields if old[key] != row[key]}
                changes.update(order_changes.get(identifier, {}))
                if changes:
                    self.add_activity(db, identifier, 'update', author, changes=changes)
            for identifier in sorted(previous.keys() | current.keys()):
                old, new = previous.get(identifier, {}), current.get(identifier, {})
                old_parent, new_parent = old.get('milestone_id'), new.get('milestone_id')
                if old_parent != new_parent:
                    for parent, verb in ((old_parent,'Unassigned'), (new_parent,'Assigned')):
                        if parent in current:
                            self.add_activity(db,parent,'update',author,f'{verb} #C{identifier:02d}: {new.get("title",old.get("title"))}.')
            db.execute('UPDATE task_board_revision SET revision=revision+1 WHERE id=1')
            return self.snapshot(db)
