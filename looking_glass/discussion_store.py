"""SQLite connection and backwards-compatible discussion schema ownership."""
import sqlite3
from contextlib import contextmanager


class DiscussionStore:
    def __init__(self, db_path):
        self.db = db_path
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots(path TEXT PRIMARY KEY, content TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS threads(
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL, start INTEGER NOT NULL,
                    end INTEGER NOT NULL, quote TEXT NOT NULL, anchor_status TEXT NOT NULL DEFAULT 'attached',
                    resolved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE INDEX IF NOT EXISTS threads_path ON threads(path);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES threads(id),
                    author TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')
            db.execute('CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id)')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(threads)')}
            if 'anchor_kind' not in columns:
                db.execute("ALTER TABLE threads ADD COLUMN anchor_kind TEXT NOT NULL DEFAULT 'source'")
            if 'render_anchor' not in columns:
                db.execute('ALTER TABLE threads ADD COLUMN render_anchor TEXT')
            if 'target_ref' not in columns:
                db.execute('ALTER TABLE threads ADD COLUMN target_ref TEXT')


    @contextmanager
    def connection(self):
        with sqlite3.connect(self.db, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            yield db

