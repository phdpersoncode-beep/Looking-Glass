"""Managed Markdown images with immutable originals and optimistic updates."""
import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
import hashlib
import math
import os
import tempfile
import secrets
import stat
from pathlib import Path
from .workspace import Problem
from .attachments import Attachments

MAX_IMAGE = 32 * 1024 * 1024


class Images:
    def __init__(self, ws):
        self.ws = ws
        self.directory = ws.meta / "images"
        self.directory.mkdir(mode=0o700, exist_ok=True)
        with ws.connection() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS images(
                id TEXT PRIMARY KEY, name TEXT NOT NULL, media_type TEXT NOT NULL,
                original BLOB NOT NULL, current BLOB NOT NULL, version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS image_sources(
                path TEXT PRIMARY KEY, image_id TEXT NOT NULL REFERENCES images(id), current_path TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS image_comments(
                thread_id INTEGER PRIMARY KEY REFERENCES threads(id) ON DELETE CASCADE,
                image_id TEXT NOT NULL REFERENCES images(id), x REAL NOT NULL, y REAL NOT NULL);''')

    def publish(self, identifier, name, raw):
        """Atomic disk copy; the database remains the recovery source."""
        target = self.directory / (identifier + '_' + name)
        fd, temporary = tempfile.mkstemp(dir=self.directory)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(raw)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return target

    def import_file(self, path):
        with self.ws.lock, self.ws.connection() as db:
            source = db.execute('SELECT * FROM image_sources WHERE path=? OR current_path=?', (path, path)).fetchone()
            if source:
                row = self.get(source['image_id'])
                file = self.ws.path(source['current_path'])
                raw = file.read_bytes() if file.stat().st_size <= MAX_IMAGE else b''
                if raw == row['current']: return self.public(row)
                # A replacement is a new image identity; old geometry must not
                # silently attach to different pixels. Keep the old original.
                with file.open('rb') as stream: image = self.add(stream, file.name)
                db.execute('UPDATE images SET version=? WHERE id=?', (secrets.token_hex(32), row['id']))
                db.execute('UPDATE image_sources SET image_id=? WHERE path=?', (image['id'], source['path']))
                db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE id IN (SELECT thread_id FROM image_comments WHERE image_id=?) AND instr(quote,?)=0", (row['id'], row['id']))
                return image
            file = self.ws.path(path)
            if not file.resolve().is_relative_to(self.ws.root):
                raise Problem('Embedded images must be inside the workspace.', 403)
            with file.open('rb') as stream: image = self.add(stream, file.name)
            db.execute('INSERT INTO image_sources VALUES(?,?,?)', (path, image['id'], path))
        return image

    @staticmethod
    def validate(raw):
        if len(raw) > MAX_IMAGE:
            raise Problem('Images are limited to 32 MiB.', 413)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in ('PNG', 'JPEG') or image.width * image.height > 40_000_000:
                        raise Problem('Use PNG or JPEG images up to 40 megapixels.', 415)
                    media_type = Image.MIME[image.format]
                    image.load()
            return media_type
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
            raise Problem('Paste a valid PNG or JPEG image.', 415)

    @staticmethod
    def public(row):
        return {key: row[key] for key in ('id', 'name', 'media_type', 'version')}

    def get(self, identifier):
        with self.ws.connection() as db:
            row = db.execute('SELECT * FROM images WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise Problem('Image not found.', 404)
        return dict(row)

    def add(self, stream, name):
        raw = stream.read(MAX_IMAGE + 1)
        media_type = self.validate(raw)
        name = Attachments.name(name or 'screenshot.png')
        if len(name.encode('utf-8')) > 180: raise Problem('Use an image name of at most 180 UTF-8 bytes.')
        name = Path(name).stem + ('.png' if media_type == 'image/png' else '.jpeg' if Path(name).suffix.lower()=='.jpeg' else '.jpg')
        identifier = hashlib.sha256(secrets.token_bytes(32) + raw).hexdigest()
        with self.ws.lock, self.ws.connection() as db:
            db.execute('INSERT INTO images VALUES(?,?,?,?,?,?)',
                       (identifier, name, media_type, raw, raw, hashlib.sha256(raw).hexdigest()))
        self.publish(identifier, name, raw)
        return self.public(self.get(identifier))

    def update(self, identifier, version, raw=None, name=None, restore=False):
        with self.ws.lock, self.ws.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.get(identifier)
            if version != row['version']:
                raise Problem('Image changed. Reopen it before saving.', 409)
            sources = db.execute('SELECT * FROM image_sources WHERE image_id=?', (identifier,)).fetchall()
            for source in sources:
                file = self.ws.path(source['current_path'])
                if file.stat().st_size > MAX_IMAGE or file.read_bytes() != row['current']:
                    raise Problem('Image changed on disk. Refusing to overwrite external changes.', 409)
            if name is not None:
                name = Attachments.name(name)
                if len(name.encode('utf-8')) > 180: raise Problem('Use an image name of at most 180 UTF-8 bytes.')
                suffix = '.png' if row['media_type'] == 'image/png' else '.jpg'
                name = Path(name).stem + suffix
            else:
                name = row['name']
            for source in sources:
                target = self.ws.path(source['current_path']).with_name(name)
                if target.name != Path(source['current_path']).name and target.exists():
                    raise Problem('A file with that name already exists.', 409)
            raw = row['original'] if restore else raw if raw is not None else row['current']
            media_type = self.validate(raw)
            with Image.open(io.BytesIO(raw)) as updated, Image.open(io.BytesIO(row['original'])) as original:
                if ImageOps.exif_transpose(updated).size != ImageOps.exif_transpose(original).size:
                    raise Problem('Annotations must preserve the image dimensions.')
            # Include metadata and a nonce so concurrent renames/restores conflict too.
            version = hashlib.sha256(raw + secrets.token_bytes(32)).hexdigest()
            db.execute('UPDATE images SET current=?,media_type=?,name=?,version=? WHERE id=?',
                       (raw, media_type, name, version, identifier))
            self.publish(identifier, name, raw)
            for source in sources:
                file = self.ws.path(source['current_path'])
                target = file.with_name(name)
                fd, temporary = tempfile.mkstemp(dir=target.parent)
                try:
                    with os.fdopen(fd, 'wb') as output: output.write(raw)
                    os.chmod(temporary, stat.S_IMODE(file.stat().st_mode))
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary): os.unlink(temporary)
                if file != target: file.unlink()
                db.execute('UPDATE image_sources SET current_path=? WHERE path=?',
                           (target.relative_to(self.ws.root).as_posix(), source['path']))
        if row['name'] != name:
            (self.directory / (identifier + '_' + row['name'])).unlink(missing_ok=True)
        return self.public(self.get(identifier))

    def comment(self, identifier, data):
        self.get(identifier)
        x, y = data.get('x'), data.get('y')
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in (x, y)):
            raise Problem('Image coordinates must be between zero and one.')
        with self.ws.lock:
            review = data.get('review_id')
            content = self.ws.reviews.read(review)['content'] if review else self.ws.text(data.get('path'))[0]
            start, end = data.get('start'), data.get('end')
            with self.ws.connection() as db:
                sources = [value for r in db.execute('SELECT path,current_path FROM image_sources WHERE image_id=?', (identifier,)) for value in r]
            from urllib.parse import unquote
            reference = data.get('reference')
            source_match = False
            if isinstance(reference, str) and reference:
                document_path = self.ws.reviews.read(review)['path'] if review else data.get('path')
                resolved = os.path.normpath(str(Path(document_path).parent / unquote(reference)))
                source_match = resolved in sources and type(start) is int and type(end) is int and reference in content[start:end]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content) or not (identifier in content[start:end] or source_match):
                raise Problem('Select the image embed in the current document.')
            if review:
                thread = self.ws.reviews.create_thread(review, data.get('version'), start, end, data.get('body'), data.get('author'))
            else:
                thread = self.ws.create_thread(data.get('path'), start, end, data.get('body'), data.get('author'), data.get('version'))
            with self.ws.connection() as db:
                db.execute('INSERT INTO image_comments VALUES(?,?,?,?)', (thread['id'], identifier, x, y))
        return self.ws.get_thread(thread['id'])
