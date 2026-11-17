"""Offline, deterministic SQL snapshots of project state (never tokens or uploads)."""
import math
import os
import re
import sqlite3
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path


HEADER = '-- Looking Glass database dump v1'
REQUIRED = {
    'snapshots': {'path', 'content'},
    'threads': {'id', 'path', 'start', 'end', 'quote', 'resolved', 'anchor_status', 'created_at'},
    'messages': {'id', 'thread_id', 'author', 'body', 'created_at'},
}


def root_path(root):
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Choose an existing project directory.')
    return root


@contextmanager
def project_lock(root, *, serving=False):
    """Coordinate CLI servers and restores across processes, including on Windows."""
    meta = root_path(root) / '.looking-glass'
    meta.mkdir(mode=0o700, exist_ok=True)
    with closing(sqlite3.connect(meta / 'maintenance.sqlite3', timeout=0, check_same_thread=False)) as lock:
        try:
            if serving:
                lock.execute('BEGIN')
                lock.execute('PRAGMA schema_version').fetchone()  # Acquire a shared read lease.
            else:
                lock.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError as error:
            raise ValueError('Project is busy. Stop looking-glass serve before restoring, or wait for the active restore.') from error
        try:
            yield
        finally:
            lock.rollback()


def state_path(root):
    return root_path(root) / '.looking-glass' / 'state.sqlite3'


def readonly(path):
    # URI encoding matters for project names containing spaces, #, or ?.
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)


def identifier(name):
    return '"' + name.replace('"', '""') + '"'


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bytes):
        return "X'" + value.hex().upper() + "'"
    if isinstance(value, str):
        # Keep each row on one physical line, including multiline prose and NULs.
        controls = [('\n', 'n'), ('\r', 'r'), ('\0', '0')]
        escape = '\\'
        while any(escape + code in value for _, code in controls):
            escape += '\\'
        encoded = value
        for character, code in controls:
            encoded = encoded.replace(character, escape + code)
        expression = "'" + encoded.replace("'", "''") + "'"
        # Bounded nesting avoids SQLite's expression-depth limit on long files;
        # concatenating once per newline would fail for ordinary large documents.
        for character, code in controls:
            if character in value:
                expression = f"replace({expression},'{escape + code}',char({ord(character)}))"
        return expression
    if isinstance(value, float) and math.isinf(value):
        return '-9.0e999' if value < 0 else '9.0e999'
    return repr(value)


def inspect(db):
    """Check physical integrity, schema identity, and all declared relationships."""
    objects = db.execute("SELECT type,name,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*'").fetchall()
    if any(kind not in ('table', 'index') or (sql and re.search(r'CREATE\s+VIRTUAL', sql, re.I))
           for kind, _, sql in objects):
        raise ValueError('Database must contain ordinary tables and indexes only.')
    tables = sorted(name for kind, name, _ in objects if kind == 'table')
    for table, required in REQUIRED.items():
        columns = {row[1] for row in db.execute(f'PRAGMA table_info({identifier(table)})')}
        if not required <= columns:
            raise ValueError(f'Not a Looking Glass database: missing {table} table or columns.')
    integrity = [row[0] for row in db.execute('PRAGMA integrity_check')]
    foreign_keys = [list(row) for row in db.execute('PRAGMA foreign_key_check')]
    if integrity != ['ok'] or foreign_keys:
        raise ValueError(f'Database check failed: integrity={integrity}; foreign_keys={foreign_keys}')
    return dict(ok=True, integrity_check=integrity, foreign_key_check=foreign_keys,
                tables={table: db.execute(f'SELECT count(*) FROM {identifier(table)}').fetchone()[0]
                        for table in tables})


def check(root):
    with closing(readonly(state_path(root))) as db:
        db.execute('BEGIN')
        result = inspect(db)
        # Upload bytes are deliberately outside the database snapshot.
        missing = []
        if 'attachments' in result['tables']:
            directory = state_path(root).parent / 'attachments'
            for key, size in db.execute('SELECT storage_key,size FROM attachments ORDER BY id'):
                file = directory / key
                if not re.fullmatch(r'[0-9a-f]{48}', key) or not file.is_file() or file.stat().st_size != size:
                    missing.append(key)
        result['warnings'] = ([f'{len(missing)} attachment file(s) missing or size mismatched; upload bytes are not in SQL dumps.']
                              if missing else [])
        return result


def dump(root, output):
    """Use SQLite backup for a consistent snapshot, including committed WAL data."""
    with tempfile.TemporaryDirectory(prefix='looking-glass-dump-') as directory:
        with closing(readonly(state_path(root))) as source, closing(sqlite3.connect(Path(directory) / 'snapshot.sqlite3')) as db:
            source.backup(db)
            result = inspect(db)
            output.write(HEADER + '\nPRAGMA foreign_keys=OFF;\nBEGIN TRANSACTION;\n')
            output.write(f'PRAGMA user_version={db.execute("PRAGMA user_version").fetchone()[0]};\n')
            for table in result['tables']:
                sql = db.execute('SELECT sql FROM sqlite_schema WHERE type=\'table\' AND name=?', (table,)).fetchone()[0]
                output.write(sql.rstrip(';') + ';\n')
            for table in result['tables']:
                columns = db.execute(f'PRAGMA table_info({identifier(table)})').fetchall()
                names = ','.join(identifier(row[1]) for row in columns)
                keys = sorted((row for row in columns if row[5]), key=lambda row: row[5])
                order = keys + [row for row in columns if not row[5]]
                ordering = ','.join(identifier(row[1]) + ' COLLATE BINARY' for row in order)
                for row in db.execute(f'SELECT {names} FROM {identifier(table)} ORDER BY {ordering}'):
                    output.write(f'INSERT INTO {identifier(table)}({names}) VALUES({",".join(map(literal, row))});\n')
            for (sql,) in db.execute("SELECT sql FROM sqlite_schema WHERE type='index' AND sql IS NOT NULL ORDER BY name"):
                output.write(sql.rstrip(';') + ';\n')
            output.write('COMMIT;\nPRAGMA foreign_keys=ON;\n')
            return result


def dump_file(root, path):
    root = root_path(root)
    path = Path(path).expanduser().absolute()
    if path.resolve().is_relative_to((root / '.looking-glass').resolve()):
        raise ValueError('Save the SQL dump outside .looking-glass so it can be tracked separately.')
    # Do not truncate an earlier snapshot if validation or writing fails.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=path.parent,
                                         prefix='.' + path.name + '-', delete=False) as output:
            temporary = Path(output.name)
            result = dump(root, output)
        os.replace(temporary, path)
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore_authorizer(action, first, second, database, trigger):
    # Imported SQL only builds an inert database in a disposable directory.
    # Deny ATTACH, triggers, virtual tables, extension loading and arbitrary functions.
    allowed = {sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_REINDEX, sqlite3.SQLITE_INSERT,
               sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_TRANSACTION}
    if action in allowed:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_UPDATE and first == 'sqlite_master':
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and second in ('char', 'replace'):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and first in ('foreign_keys', 'user_version'):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def restore(root, sql, force=False):
    root = root_path(root)
    if not sql.startswith(HEADER + '\n'):
        raise ValueError('Not a supported Looking Glass SQL dump (expected v1 header).')
    with tempfile.TemporaryDirectory(prefix='looking-glass-restore-') as directory:
        with closing(sqlite3.connect(Path(directory) / 'restored.sqlite3')) as candidate:
            candidate.execute('PRAGMA trusted_schema=OFF')
            candidate.set_authorizer(restore_authorizer)
            try:
                candidate.executescript(sql)
            finally:
                candidate.set_authorizer(None)
            if candidate.in_transaction:
                raise ValueError('Incomplete SQL dump: transaction was not committed.')
            result = inspect(candidate)
            with project_lock(root):
                destination = state_path(root)
                backup = None
                if destination.exists():
                    if not force:
                        raise ValueError('Project already has a database. Use --force to back it up and replace it.')
                    # The backup API includes WAL contents without copying live sidecars.
                    with tempfile.NamedTemporaryFile(prefix='state-backup-', suffix='.sqlite3',
                                                     dir=destination.parent, delete=False) as file:
                        backup = Path(file.name)
                    with closing(readonly(destination)) as previous, closing(sqlite3.connect(backup)) as saved:
                        previous.backup(saved)
                # SQLite replaces the destination in a transaction, preserving existing
                # connections/WAL bookkeeping rather than swapping or deleting files.
                with closing(sqlite3.connect(destination, timeout=10)) as target:
                    candidate.backup(target)
                return dict(result, backup=str(backup) if backup else None)
