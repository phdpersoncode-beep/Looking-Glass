"""Server and local agent interface. The CLI uses the same HTTP API as the UI."""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .projects import known_projects, project_root, project_url, register_project


def api(root, url, route, method='GET', data=None, timeout=15):
    token = (root/'.looking-glass'/'token').read_text().strip()
    req = Request(url + '/api/' + route,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={'Content-Type':'application/json', 'X-Looking-Glass-Token':token}, method=method)
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def check_project(root, url, timeout=15):
    project = api(root, url, 'project', timeout=timeout)
    if project['root'] != str(root):
        raise ValueError(f'Server has a different project open: {project["root"]}. Use projects list to find its address.')


def project_status(project):
    try:
        root = Path(project['root'])
        url = project_url(root, project['url'])
        check_project(root, url, timeout=1)
        return {**project, 'reachable':True}
    except (OSError, URLError, ValueError) as e:
        return {**project, 'reachable':False, 'error':str(e)}


def source_selection(parser, file, quote, occurrence):
    from .anchors import occurrences
    if occurrence is not None and occurrence < 1:
        parser.error('Occurrence is out of range; use a one-based positive number.')
    # Only enumerate enough hits to establish uniqueness or reach the chosen one.
    hits = occurrences(file['content'], quote, limit=occurrence if occurrence is not None else 2)
    if not quote or not hits or (len(hits) > 1 and occurrence is None):
        parser.error('Quote is empty, missing, or ambiguous. Provide --occurrence for a repeated quote.')
    occurrence = occurrence if occurrence is not None else 1
    if occurrence > len(hits):
        parser.error('Occurrence is out of range.')
    start = hits[occurrence-1]
    return dict(start=start, end=start+len(quote), version=file['version'])


def build_parser():
    parser = argparse.ArgumentParser(
        prog='looking-glass', description='Open local projects and review anchored discussions with coding agents.',
        epilog='Start here: looking-glass projects list; looking-glass agent --help. Agent commands require a running server.')
    sub = parser.add_subparsers(dest='command', required=True)

    def command(parent, name, help, example, description=None):
        return parent.add_parser(name, help=help, description=description or help,
                                 epilog='Example: ' + example)

    serve = command(sub, 'serve', 'Serve a local project on loopback and register its address.',
                    'looking-glass serve ~/project --port 8766')
    serve.add_argument('directory', type=Path, help='Existing project directory to open.')
    serve.add_argument('--port', type=int, default=8765, help='Local HTTP port (default: 8765).')

    projects = command(sub, 'projects', 'Discover known local projects and inspect their files.',
                       'looking-glass projects list')
    project_ops = projects.add_subparsers(dest='operation', required=True)
    command(project_ops, 'list', 'Return known roots, server URLs, and reachability as JSON.',
            'looking-glass projects list',
            'List projects registered by serve or the browser directory switch. Probe each saved address. Stopped projects remain listed.')
    show = command(project_ops, 'show', 'Show a running project, its file paths, and thread counts as JSON.',
                   'looking-glass projects show ~/project',
                   'Inspect a running project. Omit the directory to infer the nearest project from the current directory.')
    show.add_argument('directory', nargs='?', type=Path, help='Project directory; defaults to the nearest project ancestor.')
    show.add_argument('--url', help='Override the registered HTTP loopback server address.')

    agent = command(sub, 'agent', 'Read, search, and update discussions through the local HTTP API.',
                    'looking-glass agent --root ~/project list --status open',
                    'Use a running local project. Infer the nearest project from the current directory, or set --root. '
                    'Use its registered address, or set --url. Put --root and --url before the operation. '
                    'Results are JSON, except instructions, which prints text. Errors go to stderr with a nonzero exit code.')
    agent.add_argument('--root', type=Path, help='Project root; defaults to the nearest project ancestor.')
    agent.add_argument('--url', help='Override the registered address (fallback: http://127.0.0.1:8765).')
    operations = agent.add_subparsers(dest='operation', required=True)
    for name in ('list', 'search'):
        op = command(operations, name,
                     'List paginated thread summaries.' if name == 'list' else 'Search comment bodies and anchored quotes.',
                     'looking-glass agent list --status open' if name == 'list' else 'looking-glass agent search "shebang" --status open',
                     'Return JSON with threads, total, limit, offset, and next_offset, ordered by thread ID. '
                     'Filters combine. Search uses literal case-insensitive text. Use read for full messages and passage context.')
        if name == 'search':
            op.add_argument('query', help='Literal text to find in any comment body or anchored quote.')
        op.add_argument('--path', help='Exact workspace-relative file path, or a canonical absolute path for an outside file.')
        op.add_argument('--status', choices=('all', 'open', 'resolved'), default='all', help='Thread status (default: all).')
        op.add_argument('--author', help='Match a thread with any message by this author; exact, case-insensitive label.')
        op.add_argument('--anchor-status', choices=('attached', 'needs_reattachment'), help='Filter by anchor attachment status.')
        op.add_argument('--limit', type=int, default=50, help='Threads per page, 1–1000 (default: 50).')
        op.add_argument('--offset', type=int, default=0, help='Number of matching threads to skip (default: 0).')
        op.add_argument('--full', action='store_true', help='Include full thread fields and all messages instead of compact summaries.')
    read = command(operations, 'read', 'Read a thread, all messages, and current passage context.',
                   'looking-glass agent read 4 --context-lines 10',
                   'Return a JSON thread with context. Source context includes one-based line numbers and a current file version. '
                   'Rendered HTML context contains visible quote, prefix, and suffix. Detached anchors have no source context.')
    read.add_argument('id', type=int, help='Thread ID from list, search, or create.')
    read.add_argument('--context-lines', type=int, default=10, help='Source lines before and after the passage, 0–100 (default: 10).')
    create = command(operations, 'create', 'Create a discussion anchored to an exact source passage.',
                     'looking-glass agent create notes.md --quote "A passage" --author Agent --body "Please explain."')
    create.add_argument('path', help='Workspace-relative text file path, or canonical absolute outside path.')
    create.add_argument('--author', default='Agent', help='Comment author label (default: Agent).')
    reattach = command(operations, 'reattach', 'Reattach an existing source thread to an exact current passage.',
                       'looking-glass agent reattach 4 --quote "The replacement passage"',
                       'Read the discussion and original context before choosing the replacement. '
                       'Keep messages, original review context, and resolved/open state. '
                       'Rendered HTML threads must be reattached by selecting visible text in the browser.')
    reattach.add_argument('id', type=int, help='Thread ID from list, search, or read, including an already attached thread.')
    for op in (create, reattach):
        op.add_argument('--quote', required=True, help='Exact nonempty source passage; must be unique unless --occurrence is set.')
        op.add_argument('--occurrence', type=int, help='One-based occurrence to select when the quote repeats.')

    reply = command(operations, 'reply', 'Append a comment to an existing thread.',
                    'looking-glass agent reply 4 --author Agent --body "Here is my explanation."')
    reply.add_argument('id', type=int, help='Thread ID from list, search, or create.')
    reply.add_argument('--author', default='Agent', help='Comment author label (default: Agent).')
    for op in (create, reply):
        bodies = op.add_mutually_exclusive_group(required=True)
        bodies.add_argument('--body', help='Literal text. Use single shell quotes for Markdown: double quotes execute backticks and $(...).')
        bodies.add_argument('--body-file', type=Path, help='Read UTF-8 text from a file; use - for standard input.')
        bodies.add_argument('--body-stdin', action='store_true', help='Read text from standard input. Use a quoted here-document to preserve backticks.')
    for name in ('resolve', 'reopen'):
        op = command(operations, name,
                     'Mark a completed thread as resolved.' if name == 'resolve' else 'Mark a resolved thread as open again.',
                     f'looking-glass agent {name} 4')
        op.add_argument('id', type=int, help='Thread ID from list, search, or create.')
    delete = command(operations, 'delete', 'Permanently delete a thread or one comment.',
                     'looking-glass agent delete 4 --message 8',
                     'Delete the whole thread unless --message is supplied. Deleting its last message also removes the thread.')
    delete.add_argument('id', type=int, help='Thread ID to delete or modify.')
    delete.add_argument('--message', type=int, help='Delete only this message ID, obtained from read.')
    command(operations, 'instructions', 'Print copyable agent instructions for the current workspace.',
            'looking-glass agent instructions')
    review = command(operations,'review','Read and edit persistent review drafts without writing source files.',
                     'looking-glass agent review list')
    review_ops = review.add_subparsers(dest='review_operation',required=True)
    command(review_ops,'list','List pending review drafts.','looking-glass agent review list')
    for name in ('read','history','edit'):
        op = command(review_ops,name,{'read':'Read a review draft and its current revision.',
            'history':'Read chronological edits with authors and UTC timestamps.',
            'edit':'Apply sequential Unicode-code-point edits with a revision check.'}[name],
            f'looking-glass agent review {name} 1')
        op.add_argument('id',type=int,help='Review ID from review list.')
        if name=='history':
            op.add_argument('--after',type=int,default=0); op.add_argument('--limit',type=int,default=100)
        if name=='edit':
            op.add_argument('--version',required=True,help='Exact version from the latest review read.')
            op.add_argument('--author',default='Agent')
            op.add_argument('--operations-file',type=Path,required=True,
                help='UTF-8 JSON array of {start,end,insert}, applied sequentially; - reads stdin.')
    create.add_argument('--review',type=int,help='Anchor the comment in this review draft instead of the disk file.')
    for name in ('list','search'):
        # Operations are parser objects, not separate transport mechanisms.
        operations.choices[name].add_argument('--review',type=int,help='Include draft discussions and review-local passage positions.')
    operations.choices['read'].add_argument('--review',type=int,help='Read passage context from this review.')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            from .app import create_app
            from werkzeug.serving import run_simple
            if not 1 <= args.port <= 65535:
                parser.error('Port must be 1–65535.')
            app = create_app(args.directory)
            root = app.extensions['workspace'].root
            url = f'http://127.0.0.1:{args.port}'
            app.config['LOCAL_SERVER_URL'] = url
            register_project(root, url)
            print(f'Looking Glass · {root}\nOpen {url}', flush=True)
            run_simple('127.0.0.1', args.port, app, threaded=True, use_debugger=False, use_reloader=False)
            return
        if args.command == 'projects' and args.operation == 'list':
            print(json.dumps([project_status(p) for p in known_projects()], indent=2, ensure_ascii=False))
            return
        root = project_root(args.directory if args.command == 'projects' else args.root)
        url = project_url(root, args.url)
        check_project(root, url)

        def call(route, method='GET', data=None):
            return api(root, url, route, method, data)

        if args.command == 'projects':
            result = call('workspace')
            result.update(url=url, reachable=True, thread_counts={
                status:call('threads?' + urlencode({'status':status, 'limit':1}))['total']
                for status in ('all', 'open', 'resolved')})
        elif args.operation == 'instructions':
            print(call('agent-instructions')['instructions'])
            return
        elif args.operation == 'review':
            if args.review_operation=='list': result=call('reviews')
            elif args.review_operation=='read': result=call(f'reviews/{args.id}')
            elif args.review_operation=='history': result=call(f'reviews/{args.id}/edits?'+urlencode(dict(after=args.after,limit=args.limit)))
            else:
                raw=sys.stdin.read() if str(args.operations_file)=='-' else args.operations_file.read_text(encoding='utf-8')
                result=call(f'reviews/{args.id}','PATCH',dict(version=args.version,operations=json.loads(raw),author=args.author,role='agent'))
        elif args.operation in ('list', 'search'):
            query = dict(status=args.status, limit=args.limit, offset=args.offset,
                         summary='false' if args.full else 'true')
            if args.review is not None: query['review']=args.review
            for key, value in (('path', args.path), ('author', args.author),
                               ('anchor_status', args.anchor_status), ('q', getattr(args, 'query', None))):
                if value is not None:
                    query[key] = value
            result = call('threads?' + urlencode(query))
        elif args.operation == 'read':
            query={'context_lines':args.context_lines}
            if args.review is not None: query['review']=args.review
            result = call(f'threads/{args.id}?' + urlencode(query))
        elif args.operation == 'reattach':
            thread = call(f'threads/{args.id}')
            if thread['anchor_kind'] != 'source':
                parser.error('Rendered HTML anchors require selecting the replacement text in the browser.')
            file = call('file?' + urlencode({'path':thread['path']}))
            selection = source_selection(parser, file, args.quote, args.occurrence)
            result = call(f'threads/{args.id}', 'PATCH', selection)
        elif args.operation in ('create', 'reply'):
            if args.body_file is not None and str(args.body_file) != '-':
                message_body = args.body_file.expanduser().read_text(encoding='utf-8')
            elif args.body_stdin or args.body_file is not None:
                message_body = sys.stdin.read()
            else:
                message_body = args.body
            if args.operation == 'reply':
                result = call(f'threads/{args.id}/replies', 'POST', dict(body=message_body, author=args.author))
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return
            file = call(f'reviews/{args.review}') if args.review else call('file?' + urlencode({'path':args.path}))
            if file.get('path')!=args.path: parser.error('Review belongs to another file.')
            selection = source_selection(parser, file, args.quote, args.occurrence)
            result = call('threads', 'POST', dict(path=args.path, **selection, author=args.author, body=message_body,
                          **({'review_id':args.review} if args.review else {})))
        elif args.operation == 'delete':
            route = f'threads/{args.id}' + (f'/messages/{args.message}' if args.message is not None else '')
            result = call(route, 'DELETE')
        else:
            result = call(f'threads/{args.id}', 'PATCH', dict(resolved=args.operation == 'resolve'))
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except HTTPError as e:
        print(e.read().decode(), file=sys.stderr)
        raise SystemExit(1)
    except (URLError, OSError, ValueError) as e:
        print(f'Cannot access local project: {e}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
