import hashlib
import secrets
import time
import json
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from .revisions import Revisions
from .workspace import Problem, Workspace, directories
from .instructions import agent_instructions as instructions_text
from .projects import register_project


def create_app(root):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=10*1024*1024, TRUSTED_HOSTS=['127.0.0.1','localhost','[::1]'])
    ws = Workspace(root)
    git = Revisions(ws)
    previews = {}
    app.extensions['workspace'] = ws

    @app.before_request
    def protect():
        if request.method=='POST' and request.path.endswith('/attachments'):
            request.max_content_length=65*1024*1024
        if request.path.startswith(('/api/', '/fragments/')):
            if not secrets.compare_digest(request.headers.get('X-Looking-Glass-Token',''), ws.token):
                raise Problem('Missing or invalid local API token.', 401)
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                raise Problem('Cross-origin requests are not allowed.', 403)

    @app.after_request
    def security(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Static assets revalidate on each load, so a rebuild shows after a refresh.
        response.headers['Cache-Control'] = 'no-cache' if request.path.startswith('/static/') else 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.path.startswith('/preview/'):
            response.headers['Content-Security-Policy'] = "sandbox allow-scripts allow-forms allow-modals; default-src https: data: blob:; script-src https: 'unsafe-inline' 'unsafe-eval' blob:; style-src https: 'unsafe-inline'; connect-src https:; img-src https: data: blob:; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'"
        else:
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self' about: blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.errorhandler(Problem)
    def problem(e):
        return jsonify(error=str(e)), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error=e.description), e.code

    @app.errorhandler(OSError)
    def filesystem_error(e):
        return jsonify(error='Filesystem operation failed: ' + str(e)), 409

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data,dict):
            raise Problem('Send a JSON object.')
        return data

    @app.get('/')
    def index():
        # Versioned asset URLs bypass copies cached before a rebuild.
        version = max(int((Path(app.static_folder)/name).stat().st_mtime) for name in ('app.js', 'style.css'))
        return render_template('index.html', root=str(ws.root), token=ws.token, version=version)

    @app.get('/fragments/files')
    def tree():
        files = ws.files()
        tree = {}
        for path in files:
            branch = tree
            parts = path.split('/')
            for part in parts[:-1]:
                branch = branch.setdefault(part, {})
            branch[parts[-1]] = path
        return render_template('files.html', tree=tree)

    @app.get('/api/agent-instructions')
    def agent_instructions():
        return jsonify(instructions=instructions_text(ws.root, request.host_url.rstrip('/')))

    @app.get('/api/project')
    def project():
        return jsonify(root=str(ws.root))

    @app.get('/fragments/threads')
    def discussion():
        all_files = request.args.get('scope') == 'all'
        items = ws.threads(None if all_files else request.args.get('path'))
        if all_files:
            items.sort(key=lambda t: (t['path'], t['start'], t['id']))
        return render_template('threads.html', threads=items, all_files=all_files, active=request.args.get('active',type=int))

    @app.get('/api/thread-index')
    def thread_index():
        return jsonify(ws.thread_index())

    @app.get('/api/discussions')
    def discussions():
        # Browsing discussions must not reread every document. Opening/polling
        # the active file reconciles anchors before passage navigation.
        path=request.args.get('path') or None
        all_files=request.args.get('scope')=='all'
        items=ws.threads(None if all_files else path,reconcile=False) if all_files or path else []
        items.sort(key=lambda t:(t['path'],t['start'],t['id']))
        index=ws.thread_index()
        tag=hashlib.sha256(json.dumps([items,index],ensure_ascii=False).encode()).hexdigest()
        if request.if_none_match.contains(tag):
            return Response(status=304,headers={'ETag':'"'+tag+'"'})
        response=jsonify(threads=items,index=index,html=render_template('threads.html',threads=items,all_files=all_files,active=None))
        response.set_etag(tag)
        return response

    @app.get('/api/workspace')
    def workspace():
        return jsonify(root=str(ws.root), files=ws.files())

    @app.post('/api/workspace')
    def switch_workspace():
        nonlocal ws, git
        # Every route reads ws and git at call time, so this swap acts like a
        # restart in the new directory. The client reloads to get the new token.
        path = body().get('path')
        if not isinstance(path, str) or not path:
            raise Problem('Choose a directory.')
        ws = Workspace(directories(path)['path'])
        git = Revisions(ws)
        previews.clear()
        app.extensions['workspace'] = ws
        if app.config.get('LOCAL_SERVER_URL'):
            register_project(ws.root, app.config['LOCAL_SERVER_URL'])
        print(f'Looking Glass · {ws.root}', flush=True)
        return jsonify(root=str(ws.root))

    @app.get('/api/directories')
    def list_directories():
        return jsonify(directories(request.args.get('path') or str(ws.root)))

    @app.get('/api/locate')
    def locate():
        return jsonify(path=ws.locate(request.args.get('path')))

    @app.get('/api/file')
    def read_file():
        if request.args.get('version') and ws.unchanged(request.args.get('path'),request.args['version']):
            return Response(status=304)
        return jsonify(ws.read(request.args.get('path')))

    @app.put('/api/file')
    def save_file():
        data = body()
        return jsonify(ws.save(data.get('path'),data.get('content'),data.get('version')))

    @app.get('/api/binary')
    def binary():
        p = ws.path(request.args.get('path'))
        types = {'.stl':'application/octet-stream', '.png':'image/png', '.jpg':'image/jpeg',
                 '.jpeg':'image/jpeg', '.svg':'image/svg+xml'}
        if p.suffix.lower() not in types:
            raise Problem('Choose an STL, PNG, JPEG, or SVG file.')
        if p.stat().st_size > 64*1024*1024:
            raise Problem('Binary viewer files are limited to 64 MiB.',413)
        return send_file(p, mimetype=types[p.suffix.lower()], as_attachment=True)

    @app.get('/api/stat')
    def file_stat():
        p = ws.path(request.args.get('path'))
        info = p.stat()
        return jsonify(version=f'{info.st_mtime_ns}:{info.st_size}',size=info.st_size)

    @app.post('/api/preview')
    def make_preview():
        data = body()
        ws.path(data.get('path'))
        if Path(data['path']).suffix.lower() not in ('.html','.htm') or not isinstance(data.get('content'),str):
            raise Problem('Choose an HTML document.')
        # A separate short-lived capability reads only this preview. It is never
        # the API token, which report scripts must not receive in their URL.
        key = secrets.token_urlsafe(24)
        now = time.monotonic()
        for stale in [k for k, (_,expires) in previews.items() if expires < now]:
            del previews[stale]
        if len(previews) >= 128:
            del previews[next(iter(previews))]
        previews[key] = (data['content'],now+3600)
        return jsonify(url='/preview/'+key)

    @app.get('/preview/<key>')
    def preview(key):
        item = previews.get(key)
        if not item or item[1] < time.monotonic():
            raise Problem('Preview expired. Switch to source and back to render again.',404)
        bridge = (Path(app.static_folder)/'html-preview.js').read_text()
        # The bridge has no API token. It only sends selections and receives
        # highlight/navigation commands through the parent window.
        config = json.dumps(dict(channel=key,parentOrigin=request.host_url.rstrip('/')))
        return Response(item[0]+'\n<script>\n(()=>{const config='+config+';\n'+bridge+'\n})();\n</script>',mimetype='text/html')

    @app.get('/api/threads')
    def threads():
        options = {key: request.args[key] for key in
                   ('status', 'q', 'author', 'anchor_status', 'limit', 'offset', 'summary')
                   if key in request.args}
        if options:
            return jsonify(ws.query_threads(path=request.args.get('path'), **options))
        return jsonify(ws.threads(request.args.get('path')))

    @app.post('/api/threads')
    def new_thread():
        data = body()
        ws.path(data.get('path'))
        if Path(data['path']).suffix.lower() in ('.stl','.jsonl','.png','.jpg','.jpeg','.svg'):
            raise Problem('This viewer does not support annotations.')
        if 'render_anchor' in data:
            return jsonify(ws.create_rendered_thread(data.get('path'),data['render_anchor'],data.get('body'),data.get('author'),data.get('version'))),201
        return jsonify(ws.create_thread(data.get('path'),data.get('start'),data.get('end'),data.get('body'),data.get('author'),data.get('version'))),201

    @app.get('/api/threads/<int:identifier>')
    def thread(identifier):
        if 'context_lines' in request.args:
            return jsonify(ws.thread_context(identifier, request.args['context_lines']))
        return jsonify(ws.get_thread(identifier))

    @app.post('/api/threads/<int:identifier>/replies')
    def reply(identifier):
        data = body()
        return jsonify(ws.reply(identifier,data.get('body'),data.get('author'))),201

    @app.patch('/api/threads/<int:identifier>')
    def update_thread(identifier):
        data = body()
        if not set(data).issubset({'resolved','start','end','version','render_anchor','render_attached'}):
            raise Problem('Unknown thread update fields.')
        return jsonify(ws.update_thread(identifier,**data))

    @app.post('/api/threads/<int:identifier>/attachments')
    def upload_attachment(identifier):
        upload=request.files.get('file')
        if upload is None:
            raise Problem('Choose a file to attach.')
        return jsonify(ws.attachments.add(identifier,upload.stream,request.form.get('name') or upload.filename)),201

    @app.get('/api/attachments/<int:identifier>')
    def download_attachment(identifier):
        item=ws.attachments.get(identifier)
        return send_file(ws.attachments.directory/item['storage_key'],mimetype=item['media_type'],
                         as_attachment=True,download_name=item['name'])

    @app.patch('/api/attachments/<int:identifier>')
    def rename_attachment(identifier):
        return jsonify(ws.attachments.rename(identifier,body().get('name')))

    @app.delete('/api/attachments/<int:identifier>')
    def delete_attachment(identifier):
        return jsonify(ws.attachments.delete(identifier))

    @app.get('/api/git')
    def git_status():
        return jsonify(git.status())

    @app.get('/api/git/baseline')
    def git_baseline():
        return jsonify(git.baseline(request.args.get('path')))

    @app.delete('/api/threads/<int:identifier>')
    def delete_thread(identifier):
        return jsonify(ws.delete_thread(identifier))

    @app.delete('/api/threads/<int:identifier>/messages/<int:message_id>')
    def delete_message(identifier, message_id):
        return jsonify(ws.delete_message(identifier,message_id))

    @app.post('/api/git/init')
    def git_init():
        return jsonify(git.init())

    @app.post('/api/git/diff')
    def git_diff():
        return jsonify(diff=git.diff(body().get('paths')))

    @app.post('/api/git/checkpoint')
    def checkpoint():
        data = body()
        return jsonify(git.checkpoint(data.get('paths'),data.get('message'))),201

    return app
