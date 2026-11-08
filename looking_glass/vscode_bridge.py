"""Optional cooperative VS Code bridge. No document bodies or disk writes from events."""
import json
import secrets
import threading
import time
from pathlib import Path
from .workspace import Problem


class Bridge:
    def __init__(self, ws):
        self.ws = ws
        self.marker = ws.meta/'vscode-paired.json'
        self.enabled = self.marker.exists()
        self.condition = threading.Condition()
        self.epoch = None
        self.token = ''
        self.expires = self.seen = 0
        self.sequence = 0
        self.states = {}
        self.queue = []
        self.pending = {}
        self.synced = False
        self.locked = set()
        if self.enabled:
            try:
                paths=json.loads(self.marker.read_text()).get('dirty',[])
                self.locked={p for p in paths if isinstance(p,str)}
            except (OSError,ValueError,TypeError): pass

    def status(self):
        with self.condition:
            live = bool(self.epoch and self.synced and time.monotonic()-self.seen < 15 and time.monotonic() < self.expires)
            return dict(enabled=self.enabled, live=live, epoch=self.epoch,
                        sequence=self.sequence, dirty=sorted(self.locked))

    def pair(self, data):
        if data.get('root') != str(self.ws.root):
            raise Problem('Open exactly the same canonical workspace directory in VS Code.', 409)
        with self.condition:
            if self.epoch and time.monotonic()-self.seen < 15:
                raise Problem('This workspace already has a paired VS Code window.', 409)
            self._cancel()
            self.epoch = secrets.token_hex(16)
            self.token = secrets.token_urlsafe(32)
            self.expires = time.monotonic()+8*60*60
            self.seen = time.monotonic()
            self.sequence = 0
            self.synced = False
            self.enabled = True
            self._persist()
            # The first complete snapshot is mandatory before writes are enabled.
            return dict(epoch=self.epoch, credential=self.token, expires_in=8*60*60)

    def _persist(self):
        temporary=self.marker.with_suffix('.tmp')
        temporary.write_text(json.dumps({'paired':True,'dirty':sorted(self.locked)}))
        temporary.chmod(0o600)
        temporary.replace(self.marker)

    def authenticate(self, token, epoch):
        if (not self.enabled or not self.token or not secrets.compare_digest(token, self.token)
                or epoch != self.epoch or time.monotonic() >= self.expires):
            raise Problem('The VS Code connection expired. Connect again.', 401)

    def snapshot(self, data):
        sequence = data.get('sequence')
        items = data.get('documents')
        if type(sequence) is not int or sequence < 1 or not isinstance(items, list) or len(items)>512:
            raise Problem('Invalid or oversized VS Code snapshot.')
        states = {}
        for item in items:
            if not isinstance(item, dict): raise Problem('Invalid document state.')
            path = item.get('path')
            if not isinstance(path, str) or Path(path).is_absolute(): raise Problem('Invalid workspace document.')
            self.ws.path(path)  # canonical workspace rules, no symlinks or metadata
            if type(item.get('dirty')) is not bool or type(item.get('version')) is not int:
                raise Problem('Invalid document state.')
            for key in ('hash', 'text_hash'):
                value = item.get(key)
                if value is not None and (not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value)):
                    raise Problem('Invalid content hash.')
            states[path] = {k:item.get(k) for k in ('dirty','version','hash','text_hash')}
        with self.condition:
            if sequence <= self.sequence: return  # harmless duplicate / late event
            # Every event carries a bounded full open-document snapshot; gaps are safe.
            locked = {p for p,s in states.items() if s['dirty'] or p in self.locked and not s['hash']}
            if self.locked!=locked:
                self.locked=locked
                self._persist()
            self.states = states
            self.sequence = sequence
            self.synced = True
            self.seen = time.monotonic()
            identifier = data.get('request_id')
            pending = self.pending.get(identifier)
            if pending and pending['kind']=='state-request': pending['result'] = True
            self.condition.notify_all()

    def _cancel(self):
        self.queue.clear()
        for pending in self.pending.values(): pending['cancelled'] = True
        self.condition.notify_all()

    def disconnect(self):
        with self.condition:
            self.enabled = False
            self.epoch = None
            self.token = ''
            self.states.clear()
            self.locked.clear()
            self.synced = False
            self.marker.unlink(missing_ok=True)
            self._cancel()

    def poll(self):
        with self.condition:
            if not self.queue: self.condition.wait(5)
            self.seen = time.monotonic()
            messages, self.queue = self.queue, []
            return dict(messages=messages, epoch=self.epoch)

    def ask(self, kind, **fields):
        with self.condition:
            if not self.status()['live']: raise Problem('VS Code status unknown. Reconnect or explicitly disconnect the bridge.', 423)
            if len(self.pending)>=16 or len(self.queue)>=32: raise Problem('VS Code bridge is busy.', 503)
            identifier = secrets.token_hex(16)
            epoch = self.epoch
            pending = dict(kind=kind)
            self.pending[identifier] = pending
            self.queue.append(dict(kind=kind, request_id=identifier, epoch=epoch, **fields))
            self.condition.notify_all()
            try:
                ready = self.condition.wait_for(lambda: 'result' in pending or pending.get('cancelled'), timeout=3)
                if not ready or pending.get('cancelled') or self.epoch!=epoch:
                    raise Problem('VS Code did not confirm current state. Your draft is preserved.', 423)
                return pending['result']
            finally:
                self.pending.pop(identifier, None)
                self.queue[:] = [m for m in self.queue if m['request_id']!=identifier]

    def guard(self, path, directory=False):
        if not self.enabled or Path(path).is_absolute(): return
        self.ask('state-request')  # a fresh response, never just a cached clean flag
        with self.condition:
            if not self.status()['live']: raise Problem('VS Code status unknown.',423)
            if any(p==path or directory and p.startswith(path+'/') for p in self.locked):
                raise Problem('Read only — unsaved changes in VS Code', 423)

    def saved(self, path, version):
        with self.condition:
            if self.enabled and len(self.queue)<32:
                self.queue.append(dict(kind='saved', path=path, hash=version, epoch=self.epoch, request_id=secrets.token_hex(16)))
                self.condition.notify_all()

    def result(self, data):
        with self.condition:
            pending = self.pending.get(data.get('request_id'))
            if pending and pending['kind']=='provider-request':
                pending['result'] = data.get('result')
                self.condition.notify_all()

    def provider(self, data):
        path = data.get('path')
        if data.get('mode')!='edit' or data.get('provider') not in ('definition','completion','hover'):
            raise Problem('Providers require a saved Edit buffer.')
        text, version = self.ws.text(path)
        if Path(path).is_absolute() or data.get('hash')!=version or data.get('content')!=text:
            raise Problem('Save and synchronize this buffer first.',409)
        line, column = data.get('line'), data.get('column')
        lines = text.split('\n')
        if type(line) is not int or type(column) is not int or not 1<=line<=len(lines) or not 0<=column<=len(lines[line-1].rstrip('\r')):
            raise Problem('Invalid provider position.')
        self.guard(path)
        before = self.epoch
        prefix=lines[line-1][:column]
        if line==1: prefix=prefix.removeprefix('\ufeff')
        state = self.states.get(path)
        if state and (state['dirty'] or state['hash']!=version): raise Problem('VS Code is not synchronized.',409)
        result = self.ask('provider-request', path=path, hash=version, provider=data['provider'],
                          position={'line':line-1,'character':len(prefix.encode('utf-16-le'))//2})
        if not isinstance(result,dict) or result.get('error'): raise Problem('VS Code provider unavailable.',503)
        current = self.states.get(path)
        if self.epoch!=before or not self.status()['live'] or path in self.locked or (current and current['version']!=result.get('version')) or self.ws.text(path)[1]!=version:
            raise Problem('The provider result became stale.',409)
        if data['provider']=='definition':
            targets=[]
            for target in result.get('definitions',[])[:64]:
                try:
                    name=target['path']
                    if Path(name).is_absolute(): continue
                    dest, dest_hash=self.ws.text(name)
                    if target.get('version')!=dest_hash: continue
                    if type(target.get('line')) is not int or type(target.get('column')) is not int: continue
                    targets.append({**target,'version':dest_hash,'column':target['column']+(1 if dest.startswith('\ufeff') and target['line']==1 else 0)})
                except (KeyError,TypeError,OSError,Problem): continue
            result['definitions']=targets
        return result


def install_routes(app, workspace, body):
    from flask import jsonify, request

    @app.post('/api/bridge/pair')
    def bridge_pair(): return jsonify(workspace().bridge.pair(body()))

    @app.get('/api/bridge/status')
    def bridge_status():
        bridge=workspace().bridge
        wait=request.args.get('wait')
        if wait:
            with bridge.condition:
                def changed():
                    state=bridge.status()
                    return json.dumps([state['epoch'],state['sequence'],state['enabled'],state['live']],separators=(',',':'))!=wait
                bridge.condition.wait_for(changed,timeout=5)
        return jsonify(bridge.status())

    @app.post('/api/bridge/disconnect')
    def bridge_disconnect():
        workspace().bridge.disconnect()
        return jsonify(disconnected=True)

    @app.post('/api/bridge/provider')
    def bridge_provider(): return jsonify(workspace().bridge.provider(body()))

    @app.route('/api/bridge/session/<action>', methods=['GET','POST'])
    def bridge_session(action):
        bridge=workspace().bridge
        with bridge.condition:
            bridge.authenticate(request.headers.get('X-Looking-Glass-Bridge',''), request.headers.get('X-Looking-Glass-Epoch',''))
            if action=='poll' and request.method=='GET': return jsonify(bridge.poll())
            if action=='snapshot' and request.method=='POST': bridge.snapshot(body())
            elif action=='result' and request.method=='POST': bridge.result(body())
            else: raise Problem('Unknown bridge message.',404)
        return jsonify(ok=True)
