"""Server and local agent interface. The CLI uses the same HTTP API as the UI."""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main(argv=None):
    parser = argparse.ArgumentParser(prog='looking-glass')
    sub = parser.add_subparsers(dest='command',required=True)
    serve = sub.add_parser('serve',help='Open a project directory on loopback')
    serve.add_argument('directory',type=Path)
    serve.add_argument('--port',type=int,default=8765)
    agent = sub.add_parser('agent',help='Read and update discussions through the local HTTP API')
    agent.add_argument('--root',type=Path,required=True,help='Project directory opened by the server')
    agent.add_argument('--url',default='http://127.0.0.1:8765')
    operations = agent.add_subparsers(dest='operation',required=True)
    ls = operations.add_parser('list')
    ls.add_argument('--path')
    read = operations.add_parser('read')
    read.add_argument('id',type=int)
    create = operations.add_parser('create')
    create.add_argument('path')
    create.add_argument('--quote',required=True,help='Unique exact passage to anchor')
    create.add_argument('--occurrence',type=int,help='1-based occurrence when the quote repeats')
    create.add_argument('--author',default='Codex')
    create.add_argument('--body',required=True)
    reply = operations.add_parser('reply')
    reply.add_argument('id',type=int)
    reply.add_argument('--author',default='Codex')
    reply.add_argument('--body',required=True)
    for command in ('resolve','reopen'):
        op = operations.add_parser(command)
        op.add_argument('id',type=int)
    args = parser.parse_args(argv)
    if args.command == 'serve':
        from .app import create_app
        from werkzeug.serving import run_simple
        app = create_app(args.directory)
        print(f'Looking Glass · {args.directory.resolve()}\nOpen http://127.0.0.1:{args.port}',flush=True)
        run_simple('127.0.0.1',args.port,app,threaded=True,use_debugger=False,use_reloader=False)
        return
    from .anchors import occurrences
    if not args.url.startswith(('http://127.0.0.1:', 'http://localhost:', 'http://[::1]:')):
        parser.error('Agent URL must be a local loopback server.')
    try:
        token = (args.root.expanduser().resolve()/'.looking-glass'/'token').read_text().strip()

        def api(route,method='GET',data=None):
            req = Request(args.url.rstrip('/') + '/api/' + route,
                          data=json.dumps(data).encode() if data is not None else None,
                          headers={'Content-Type':'application/json','X-Looking-Glass-Token':token}, method=method)
            with urlopen(req,timeout=15) as response:
                return json.load(response)

        if args.operation == 'list':
            result = api('threads' + ('?' + urlencode({'path':args.path}) if args.path else ''))
        elif args.operation == 'read':
            result = api(f'threads/{args.id}')
        elif args.operation == 'create':
            file = api('file?' + urlencode({'path':args.path}))
            hits = occurrences(file['content'],args.quote)
            if not hits or (len(hits)>1 and args.occurrence is None):
                parser.error('Quote is missing or ambiguous. Provide --occurrence for a repeated quote.')
            occurrence = args.occurrence or 1
            if not 1 <= occurrence <= len(hits):
                parser.error('Occurrence is out of range.')
            start = hits[occurrence-1]
            result = api('threads','POST',dict(path=args.path,start=start,end=start+len(args.quote),version=file['version'],author=args.author,body=args.body))
        elif args.operation == 'reply':
            result = api(f'threads/{args.id}/replies','POST',dict(body=args.body,author=args.author))
        else:
            result = api(f'threads/{args.id}','PATCH',dict(resolved=args.operation == 'resolve'))
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except HTTPError as e:
        print(e.read().decode(),file=sys.stderr)
        raise SystemExit(1)
    except (URLError,OSError) as e:
        print(f'Cannot reach local project: {e}',file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
