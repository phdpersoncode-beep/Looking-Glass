#!/usr/bin/env python3
"""Block until a human posts new activity in a Looking Glass project.

The steady state costs two small loopback requests per interval and no file
reads: the pending-review list, and a conditional GET of the thread search
index that returns 304 while nothing changed. Only a changed index triggers
one summary listing, which is then diffed against the saved state.

A thread is reported when it is open, its last message has a new ID, and that
message's author is one of the --human labels. Agent replies (including ours
and other sessions') only update the saved state, so agents never trigger
each other.

Commands:
  init   Record the current threads as seen, so only later activity counts.
  wait   Poll until activity, --max-wait, idle limit, stop request, or outage.
  stop   Ask a running `wait` to exit at its next poll.

Examples:
  lg_watch.py init --root ~/proj --human User --idle-stop 1800
  lg_watch.py wait --root ~/proj
  lg_watch.py stop --root ~/proj

Each command prints one JSON object. `wait` exits 0 with "status" set to
activity, timeout, idle, stopped, or unreachable.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

QUOTE_LIMIT = 300
OUTAGE_LIMIT = 300  # seconds of consecutive failures before giving up


def find_root(start):
    path = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(path, '.looking-glass', 'token')):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            sys.exit('No Looking Glass project found; pass --root.')
        path = parent


def state_path(root):
    base = os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state')
    name = hashlib.sha1(root.encode()).hexdigest()[:12] + '.json'
    return os.path.join(base, 'looking-glass-watcher', name)


def stop_path(root):
    return state_path(root) + '.stop'


def load_state(root):
    try:
        with open(state_path(root), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f'No watcher state for {root}; run init first.')


def save_state(root, state):
    path = state_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    os.replace(temporary, path)


def registered_url(root):
    """Registered server address; never starts a server."""
    proc = subprocess.run(['looking-glass', 'projects', 'list'], capture_output=True, text=True)
    for project in json.loads(proc.stdout or '[]'):
        if os.path.realpath(project['root']) == root:
            return project['url']
    return 'http://127.0.0.1:8765'


class Server:
    def __init__(self, root, url):
        self.url = url.rstrip('/')
        with open(os.path.join(root, '.looking-glass', 'token')) as f:
            self.token = f.read().strip()

    def get(self, route, etag=None):
        """Return (status, etag, parsed body or None)."""
        headers = {'X-Looking-Glass-Token': self.token}
        if etag:
            headers['If-None-Match'] = etag
        try:
            with urlopen(Request(self.url + '/api/' + route, headers=headers), timeout=10) as response:
                return response.status, response.headers.get('ETag'), json.load(response)
        except HTTPError as e:
            if e.code == 304:
                return 304, etag, None
            raise

    def open_threads(self, review):
        threads, offset = [], 0
        while offset is not None:
            query = dict(status='open', limit=1000, offset=offset)
            if review:
                query['review'] = review
            page = self.get('threads?' + urlencode(query))[2]
            threads += page['threads']
            offset = page['next_offset']
        return threads


def pending_reviews(server):
    """Map path -> pending review ID. Any pending ID makes listings include every draft's threads."""
    return {r['path']: r['id'] for r in server.get('reviews')[2]['reviews']}


def index_route(reviews):
    return 'thread-search-index' + (f'?review={min(reviews.values())}' if reviews else '')


def snapshot(server, reviews):
    return {str(t['id']): t['last_message']['id'] for t in server.open_threads(min(reviews.values(), default=None))}


def command_init(args, root):
    url = args.url or registered_url(root)
    server = Server(root, url)
    try:
        project = server.get('project')[2]
    except (URLError, OSError) as e:
        # A 401 means the address serves a project with another token.
        sys.exit(f'Cannot use {url} for {root}: {e}. Check `looking-glass projects list`; never start a server here.')
    if os.path.realpath(project['root']) != root:
        sys.exit(f'{url} serves {project["root"]}, not {root}. Pass --url.')
    reviews = pending_reviews(server)
    _, etag, _ = server.get(index_route(reviews))
    state = dict(root=root, url=url, humans=[h.casefold() for h in args.human],
                 idle_stop=args.idle_stop, etag=etag, etag_route=index_route(reviews),
                 seen=snapshot(server, reviews), last_activity=time.time())
    save_state(root, state)
    if os.path.exists(stop_path(root)):
        os.remove(stop_path(root))
    print(json.dumps(dict(status='ready', root=root, url=url, humans=args.human,
                          open_threads=len(state['seen']), pending_reviews=reviews,
                          state=state_path(root))))


def changes(server, state, reviews):
    """Diff open threads against state; update state; return human activity."""
    found = []
    for t in server.open_threads(min(reviews.values(), default=None)):
        key, last = str(t['id']), t['last_message']
        previous = state['seen'].get(key)
        if previous == last['id']:
            continue
        state['seen'][key] = last['id']
        if last['author'].strip().casefold() not in state['humans']:
            continue
        item = dict(id=t['id'], path=t['path'], anchor_kind=t['anchor_kind'],
                    anchor_status=t['anchor_status'], quote=t['quote'][:QUOTE_LIMIT],
                    new_thread=t['message_count'] == 1, message_count=t['message_count'],
                    last_message={k: last[k] for k in ('id', 'author', 'created_at', 'body')})
        if t['path'] in reviews:
            item['review_id'] = reviews[t['path']]
        found.append(item)
    return found


def command_wait(args, root):
    state = load_state(root)
    server = Server(root, state['url'])
    started, polls, failing_since = time.time(), 0, None
    while True:
        now = time.time()
        if os.path.exists(stop_path(root)):
            os.remove(stop_path(root))
            return dict(status='stopped')
        if now - state['last_activity'] > state['idle_stop']:
            return dict(status='idle', idle_seconds=round(now - state['last_activity']))
        try:
            reviews = pending_reviews(server)
            route = index_route(reviews)
            status, etag, _ = server.get(route, state['etag'] if route == state['etag_route'] else None)
            polls += 1
            failing_since = None
            if status == 200:
                found = changes(server, state, reviews)
                state.update(etag=etag, etag_route=route)
                if found:
                    state['last_activity'] = time.time()
                save_state(root, state)
                if found:
                    return dict(status='activity', polls=polls, threads=found)
        except (URLError, OSError, HTTPError) as e:
            failing_since = failing_since or now
            if now - failing_since > OUTAGE_LIMIT:
                return dict(status='unreachable', url=state['url'], error=str(e))
        if time.time() - started + args.interval > args.max_wait:
            return dict(status='timeout', polls=polls,
                        idle_seconds=round(time.time() - state['last_activity']))
        # Sleep in short slices so a stop request takes effect within a second.
        wake = time.time() + args.interval
        while time.time() < wake and not os.path.exists(stop_path(root)):
            time.sleep(min(1, wake - time.time()))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=('init', 'wait', 'stop'))
    p.add_argument('--root', help='Project root (default: nearest ancestor with .looking-glass/token).')
    p.add_argument('--url', help='init: server address override (default: registered address).')
    p.add_argument('--human', action='append', help='init: human author label that triggers replies; repeatable (default: User).')
    p.add_argument('--idle-stop', type=int, default=1800, help='init: seconds without human activity before wait reports idle (default: 1800).')
    p.add_argument('--interval', type=float, default=30, help='wait: seconds between polls (default: 30).')
    p.add_argument('--max-wait', type=float, default=540, help='wait: seconds before reporting timeout (default: 540, under the 10-minute Bash limit).')
    args = p.parse_args()
    root = os.path.realpath(args.root) if args.root else find_root(os.getcwd())
    if args.command == 'init':
        args.human = args.human or ['User']
        command_init(args, root)
    elif args.command == 'stop':
        load_state(root)
        open(stop_path(root), 'w').close()
        print(json.dumps(dict(status='stop_requested', root=root)))
    else:
        print(json.dumps(command_wait(args, root), ensure_ascii=False))


if __name__ == '__main__':
    main()
