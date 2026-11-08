"""Workspace-only explorer operations, retaining discussion and review history."""
import hashlib
import json
import os
import secrets
from pathlib import Path
from .workspace import EXCLUDED, Problem


class FileOperations:
    def __init__(self, ws): self.ws = ws

    def path(self, value, *, existing=True):
        if not isinstance(value, str) or not value or '\\' in value or any(ord(c)<32 for c in value):
            raise Problem('Choose a workspace path.')
        p=Path(value)
        if p.is_absolute() or '..' in p.parts or any(part in EXCLUDED for part in p.parts) or p.as_posix()=='.':
            raise Problem('Path is outside the editable workspace.',403)
        full=self.ws.root/p
        for ancestor in [full,*full.parents]:
            if ancestor==self.ws.root:break
            if ancestor.is_symlink():raise Problem('Symlink operations are not supported.',403)
        if existing and not full.exists():raise Problem('File no longer exists.',404)
        if not full.parent.is_dir():raise Problem('Choose an existing destination folder.')
        return full

    def info(self, path):
        full=self.path(path)
        entries=[full]
        if full.is_dir():
            def fail(error):raise error
            for directory,dirs,names in os.walk(full,onerror=fail):
                for name in dirs+names:
                    item=Path(directory)/name
                    if item.is_symlink() or name in EXCLUDED:raise Problem('This directory contains protected metadata or symlinks.',403)
                    entries.append(item)
                    if len(entries)>10000:raise Problem('Move at most 10000 entries at once.',413)
        signature=[]
        for item in sorted(entries):
            if item.is_symlink() or any(p in EXCLUDED for p in item.relative_to(self.ws.root).parts):
                raise Problem('This directory contains protected metadata or symlinks.',403)
            s=item.stat();signature.append((str(item.relative_to(full.parent)),s.st_ino,s.st_size,s.st_mtime_ns))
        return dict(path=full.relative_to(self.ws.root).as_posix(),directory=full.is_dir(),version=hashlib.sha256(json.dumps(signature).encode()).hexdigest())

    def change(self, path, version, destination=None, delete=False):
        with self.ws.lock:
            info=self.info(path);source=self.path(path);path=info['path']
            if version!=info['version']:raise Problem('Files changed. Reopen the menu and try again.',409)
            if delete:
                target=self.ws.meta/'trash'/secrets.token_hex(16)/'files'/source.name
                target.parent.mkdir(parents=True)
                (target.parent.parent/'restore.json').write_text(json.dumps({'path':path}))
            else:
                target=self.path(destination,existing=False)
                if target==source:return dict(path=path,destination=path,deleted=False)
                if target.exists():raise Problem('A file or folder with that name already exists.',409)
                if target.is_relative_to(source):raise Problem('A folder cannot be moved into itself.')
            new=target.relative_to(self.ws.root).as_posix()
            def remap(value):return new+value[len(path):] if value==path or value.startswith(path+'/') else value
            moved=False
            try:
                with self.ws.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if not delete:
                        # Refuse to merge histories left at a formerly occupied destination.
                        for table in ['snapshots','threads','review_drafts','review_heads','pdf_bookmarks']:
                            for row in db.execute(f'SELECT DISTINCT path FROM {table}'):
                                value=row['path']
                                if (value==new or value.startswith(new+'/')) and remap(value)==value:
                                    raise Problem('The destination has existing review history. Choose another name.',409)
                    os.rename(source,target);moved=True
                    if delete:
                        for row in db.execute('SELECT id,path FROM threads').fetchall():
                            if row['path']==path or row['path'].startswith(path+'/'):
                                db.execute("UPDATE threads SET anchor_status='needs_reattachment' WHERE id=?",(row['id'],))
                    else:
                        for table in ['snapshots','threads','review_drafts','review_heads','pdf_bookmarks']:
                            for row in db.execute(f'SELECT DISTINCT path FROM {table}').fetchall():
                                value=row['path'];mapped=remap(value)
                                if mapped!=value:db.execute(f'UPDATE {table} SET path=? WHERE path=?',(mapped,value))
                        for source_row in db.execute('SELECT * FROM image_sources').fetchall():
                            current=source_row['current_path'];mapped=remap(current)
                            if Path(mapped).name!=Path(current).name:
                                row=self.ws.images.get(source_row['image_id']);name=Path(mapped).name
                                db.execute('UPDATE images SET name=?,version=? WHERE id=?',(name,secrets.token_hex(32),row['id']))
                                self.ws.images.publish(row['id'],name,row['current'])
                        for column in ['path','current_path']:
                            for row in db.execute(f'SELECT DISTINCT {column} FROM image_sources').fetchall():
                                value=row[column];mapped=remap(value)
                                if mapped!=value:db.execute(f'UPDATE image_sources SET {column}=? WHERE {column}=?',(mapped,value))
            except BaseException:
                if moved:os.rename(target,source)
                raise
            self.ws._fingerprints.clear()
            return dict(path=path,destination=None if delete else new,deleted=delete)
