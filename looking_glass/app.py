import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from .revisions import Revisions
from .workspace import Problem, Workspace


def create_app(root):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=10*1024*1024, TRUSTED_HOSTS=['127.0.0.1','localhost','[::1]'])
    ws = Workspace(root)
    git = Revisions(ws)
    previews = {}
    app.extensions['workspace'] = ws

    @app.before_request
    def protect():
        if request.path.startswith(('/api/', '/fragments/')):
            if not secrets.compare_digest(request.headers.get('X-Looking-Glass-Token',''), ws.token):
                raise Problem('Missing or invalid local API token.', 401)
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                raise Problem('Cross-origin requests are not allowed.', 403)

    @app.after_request
    def security(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store' if not request.path.startswith('/static/') else 'public, max-age=3600'
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
        return render_template('index.html', root=str(ws.root), token=ws.token)

    @app.get('/fragments/files')
    def tree():
        return render_template('files.html', files=ws.files())

    @app.get('/fragments/threads')
    def discussion():
        return render_template('threads.html', threads=ws.threads(request.args.get('path')), active=request.args.get('active',type=int))

    @app.get('/api/workspace')
    def workspace():
        return jsonify(root=str(ws.root), files=ws.files())

    @app.get('/api/file')
    def read_file():
        return jsonify(ws.read(request.args.get('path')))

    @app.put('/api/file')
    def save_file():
        data = body()
        return jsonify(ws.save(data.get('path'),data.get('content'),data.get('version')))

    @app.get('/api/binary')
    def binary():
        p = ws.path(request.args.get('path'))
        if p.suffix.lower() != '.stl':
            raise Problem('The binary viewer accepts STL files only.')
        if p.stat().st_size > 64*1024*1024:
            raise Problem('STL files are limited to 64 MiB.',413)
        return send_file(p, mimetype='application/octet-stream', as_attachment=True)

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
        return Response(item[0],mimetype='text/html')

    @app.get('/api/threads')
    def threads():
        return jsonify(ws.threads(request.args.get('path')))

    @app.post('/api/threads')
    def new_thread():
        data = body()
        ws.path(data.get('path'))
        if Path(data['path']).suffix.lower() in ('.stl','.jsonl'):
            raise Problem('This viewer does not support annotations.')
        return jsonify(ws.create_thread(data.get('path'),data.get('start'),data.get('end'),data.get('body'),data.get('author'),data.get('version'))),201

    @app.get('/api/threads/<int:identifier>')
    def thread(identifier):
        return jsonify(ws.get_thread(identifier))

    @app.post('/api/threads/<int:identifier>/replies')
    def reply(identifier):
        data = body()
        return jsonify(ws.reply(identifier,data.get('body'),data.get('author'))),201

    @app.patch('/api/threads/<int:identifier>')
    def update_thread(identifier):
        data = body()
        if not set(data).issubset({'resolved','start','end','version'}):
            raise Problem('Unknown thread update fields.')
        return jsonify(ws.update_thread(identifier,**data))

    @app.get('/api/git')
    def git_status():
        return jsonify(git.status())

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
