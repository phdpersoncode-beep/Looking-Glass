"""Discussion projections; specialized indexes avoid file/origin/attachment work."""
import json
from dataclasses import dataclass

from .workspace import Problem


@dataclass(frozen=True)
class DiscussionScope:
    review: int | None = None
    path: str | None = None

    @property
    def across_pending(self):
        return bool(self.review and self.path is None)

    def visibility(self, alias='t'):
        column = f'{alias}.review_id'
        if self.across_pending:
            return f"({column} IS NULL OR {column} IN (SELECT id FROM review_drafts WHERE status='pending'))", ()
        if self.review:
            return f'({column} IS NULL OR {column}=?)', (self.review,)
        return f'{column} IS NULL', ()

    def anchors(self, alias='a'):
        if self.across_pending:
            return f"{alias}.review_id IN (SELECT id FROM review_drafts WHERE status='pending')", ()
        return f'{alias}.review_id=?', (self.review,)


class DiscussionQueries:
    @staticmethod
    def index_rows(db, review, fields, order):
        scope = DiscussionScope(review)
        visibility, parameters = scope.visibility()
        if review:
            anchors, anchor_parameters = scope.anchors()
            join = f' LEFT JOIN review_anchors a ON a.thread_id=t.id AND {anchors}'
        else:
            join, anchor_parameters = '', ()
        return db.execute(f'SELECT {fields} FROM threads t{join} WHERE {visibility} ORDER BY {order}',
                          (*anchor_parameters, *parameters))

    def __init__(self, workspace):
        self.ws = workspace

    def threads(self, path=None, reconcile=True, review=None):
        with self.ws.lock, self.ws.connection() as db:
            self.ws.reconciler.refresh(db, path, reconcile)
            scope = DiscussionScope(review, path)
            visibility, values = scope.visibility('threads')
            conditions, parameters = [visibility], list(values)
            if path:
                conditions.append('path=?'); parameters.append(path)
            rows = db.execute('SELECT * FROM threads WHERE ' + ' AND '.join(conditions) + ' ORDER BY start,id', parameters).fetchall()
            anchor_where, anchor_parameters = scope.anchors()
            anchors = {row['thread_id']:dict(row) for row in db.execute('SELECT a.* FROM review_anchors a WHERE '+anchor_where, anchor_parameters)} if review else {}
            messages, attachments = {}, {}
            origins = self.ws.origins.public(db,path)
            suffix = ' WHERE thread_id IN (SELECT id FROM threads WHERE path=?)' if path else ''
            for message in db.execute('SELECT * FROM messages'+suffix+' ORDER BY id',(path,) if path else ()):
                messages.setdefault(message['thread_id'],[]).append({**dict(message), 'origin':origins.get(message['origin_id']), 'commit_hash':origins.get(message['origin_id'],{}).get('commit_hash')})
            for item in db.execute('SELECT * FROM attachments'+suffix+' ORDER BY id',(path,) if path else ()):
                attachments.setdefault(item['thread_id'],[]).append(self.ws.attachments.public(item))
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
        with self.ws.connection() as db:
            start = 'COALESCE(a.start,t.start)' if review else 't.start'
            status = 'COALESCE(a.anchor_status,t.anchor_status)' if review else 't.anchor_status'
            fields = f't.id,t.path,{start} AS start,t.resolved,{status} AS anchor_status,t.anchor_kind,t.target_ref,t.review_id'
            return [dict(row) for row in self.index_rows(db,review,fields,'t.path,start,t.id')]

    def thread_search_index(self, review=None):
        """Lean search text and filters: no file reads, reconciliation, origins or attachments."""
        with self.ws.lock, self.ws.connection() as db:
            quote = 'COALESCE(a.quote,t.quote)' if review else 't.quote'
            status = 'COALESCE(a.anchor_status,t.anchor_status)' if review else 't.anchor_status'
            rows = self.index_rows(db,review,f't.id,t.path,{quote} AS quote,t.resolved,{status} AS anchor_status','t.id')
            threads = {row['id']: {**dict(row), 'resolved': bool(row['resolved']), 'messages': []}
                       for row in rows}
            for row in db.execute('SELECT thread_id,body FROM messages ORDER BY id'):
                if row['thread_id'] in threads:
                    threads[row['thread_id']]['messages'].append(dict(body=row['body']))
            return list(threads.values())

    def query_threads(self, path=None, status='all', q=None, author=None,
                      anchor_status=None, limit=50, offset=0, summary='true', review=None):
        """Shared literal, case-insensitive search with stable ID pagination."""
        if status not in ('all', 'open', 'resolved'):
            raise Problem('Status must be all, open, or resolved.')
        if anchor_status not in (None, 'attached', 'needs_reattachment'):
            raise Problem('Anchor status must be attached or needs_reattachment.')
        if summary not in ('true', 'false'):
            raise Problem('Summary must be true or false.')
        limit = self.ws.query_integer(limit, 'Limit', 1, 1000)
        offset = self.ws.query_integer(offset, 'Offset', 0)
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


