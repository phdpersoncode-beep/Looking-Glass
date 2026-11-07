"""Bounded, on-demand Python definitions; no background indexing or project execution."""
import json
import subprocess
import sys
import threading
import tempfile
from pathlib import Path

from .workspace import Problem, digest

MAX_SOURCE = 512 * 1024
TIMEOUT = 4
_worker = threading.BoundedSemaphore(1)


def definitions(ws, data):
    path = data.get('path')
    full = ws.path(path)
    if full.suffix.lower() not in {'.py', '.pyi'}:
        raise Problem('Go to definition is available in Python files.')
    content = data.get('content')
    if not isinstance(content, str) or '\x00' in content or len(content.encode('utf-8')) > MAX_SOURCE:
        raise Problem('Python navigation supports source buffers up to 512 KiB.', 413)
    line, column = data.get('line'), data.get('column')
    lines = content.split('\n')
    if type(line) is not int or type(column) is not int or not 1 <= line <= len(lines) or not 0 <= column <= len(lines[line-1].rstrip('\r')):
        raise Problem('Choose a position in the current Python buffer.')
    if not _worker.acquire(blocking=False):
        raise Problem('Python navigation is busy. Try again shortly.', 429)
    try:
        try:
            with tempfile.TemporaryDirectory(prefix='looking-glass-python-') as cache:
                completed = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('python_worker.py'))],
                                           input=json.dumps(dict(root=str(ws.root), path=str(full), content=content, line=line, column=column, cache=cache)),
                                           text=True, capture_output=True, timeout=TIMEOUT, cwd=Path(__file__).parent)
        except subprocess.TimeoutExpired:
            raise Problem('Python analysis took too long. Try a smaller file or a simpler expression.', 408)
        if completed.returncode:
            raise Problem('Python analysis could not resolve this source buffer.', 422)
        results = json.loads(completed.stdout)
    finally:
        _worker.release()
    targets, seen = [], set()
    for target in results:
        destination = Path(target['path'])
        # Navigation stays inside the served workspace; dependency/library
        # sources may be inferred, but are not opened implicitly.
        if not destination.is_relative_to(ws.root):
            continue
        key = destination.relative_to(ws.root).as_posix()
        try:
            source, version = (content, digest(content.encode('utf-8'))) if destination == full else ws.text(key)
            ws.path(key)
        except Problem:
            continue
        identity = key, target['line'], target['column']
        if identity in seen:
            continue
        seen.add(identity)
        if not 1 <= target['line'] <= len(source.split('\n')):
            continue
        targets.append({**target, 'path': key, 'version': version})
    return dict(definitions=targets)
