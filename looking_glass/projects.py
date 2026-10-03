"""Known local projects. Store addresses, never API tokens, in a user registry."""
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_URL = 'http://127.0.0.1:8765'


def local_url(value):
    """Accept only plain HTTP loopback origins, without credentials or paths."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError('Server URL must be an HTTP loopback address with a valid port.')
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or port is None or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Server URL must be an HTTP loopback address, such as http://127.0.0.1:8765.')
    return value.rstrip('/')


def registry_path():
    override = os.environ.get('LOOKING_GLASS_CONFIG_DIR')
    directory = Path(override).expanduser() if override else Path(
        os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))/'looking-glass'
    return directory/'projects.sqlite3'


def known_projects():
    path = registry_path()
    if not path.exists():
        return []
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute('SELECT root,url FROM projects ORDER BY root')]


def register_project(root, url):
    url = local_url(url)
    path = registry_path()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS projects(root TEXT PRIMARY KEY, url TEXT NOT NULL)')
        db.execute('INSERT INTO projects VALUES(?,?) ON CONFLICT(root) DO UPDATE SET url=excluded.url',
                   (str(Path(root).expanduser().resolve()), url))


def project_root(root=None):
    if root is not None:
        return Path(root).expanduser().resolve()
    current = Path.cwd().resolve()
    registered = {Path(project['root']) for project in known_projects()}
    for directory in (current, *current.parents):
        if (directory/'.looking-glass'/'token').is_file() or directory in registered:
            return directory
    raise ValueError('No Looking Glass project found here. Use --root PATH or run looking-glass projects list.')


def project_url(root, url=None):
    if url is not None:
        return local_url(url)
    for project in known_projects():
        if project['root'] == str(root):
            return local_url(project['url'])
    return DEFAULT_URL
