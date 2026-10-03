"""Explicit selected-path commits without staging unrelated work."""
import os
import subprocess
import tempfile
from pathlib import Path
from .workspace import Problem


class Revisions:
    def __init__(self, workspace):
        self.ws = workspace

    def git(self, *args, env=None, check=True):
        environment = {**os.environ, **(env or {}), 'GIT_LITERAL_PATHSPECS':'1'}
        p = subprocess.run(['git', '-C', str(self.ws.root), *args], capture_output=True, env=environment)
        if check and p.returncode:
            raise Problem(p.stderr.decode('utf-8', errors='replace').strip() or 'Git command failed.')
        return p

    def root(self):
        p = self.git('rev-parse', '--show-toplevel', check=False)
        return Path(p.stdout.decode().strip()) if p.returncode == 0 else None

    def status(self):
        if not self.root():
            return dict(repository=False, files=[])
        p = self.git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', '.')
        parts = p.stdout.decode('utf-8', errors='replace').split('\0')
        prefix = self.ws.root.relative_to(self.root()).as_posix()
        prefix = '' if prefix == '.' else prefix + '/'
        files, i = [], 0
        while i < len(parts):
            item = parts[i]
            i += 1
            if not item:
                continue
            code, name = item[:2], item[3:]
            if 'R' in code or 'C' in code:
                i += 1
            if not name.startswith(prefix):
                continue
            name = name[len(prefix):]
            if not any(x in name.split('/') for x in ('.looking-glass', '.git', '.venv', 'node_modules')):
                files.append(dict(path=name, status=code))
        return dict(repository=True, files=files)

    def init(self):
        if self.root():
            raise Problem('This directory already belongs to a Git repository.')
        self.git('init')
        return self.status()

    def validate_paths(self, paths):
        if not isinstance(paths, list) or not paths or any(not isinstance(p,str) for p in paths):
            raise Problem('Select at least one file.')
        selected = {f['path'] for f in self.status()['files']}
        for p in paths:
            if p not in selected:
                raise Problem('Choose files from the current change list.')
            # Deleted files are permitted, but no directories or metadata paths.
            if Path(p).is_absolute() or '..' in Path(p).parts:
                raise Problem('Invalid checkpoint path.')
        return list(dict.fromkeys(paths))

    def diff(self, paths):
        paths = self.validate_paths(paths)
        head = self.git('rev-parse','--verify','HEAD',check=False)
        pieces = []
        for p in paths:
            patch = self.git('diff', *(('HEAD',) if head.returncode == 0 else ()), '--', p).stdout.decode('utf-8', errors='replace')
            if not patch and (self.ws.root / p).is_file():
                raw = (self.ws.root / p).read_bytes()
                patch = f'New file: {p}\n' + (raw.decode('utf-8',errors='replace') if len(raw) < 200000 and b'\x00' not in raw else '[binary or large file]')
            pieces.append(patch)
        return '\n'.join(pieces)

    def checkpoint(self, paths, message):
        if not isinstance(message,str) or not message.strip() or len(message)>500:
            raise Problem('Give the checkpoint a name of 1–500 characters.')
        with self.ws.lock:
            if not self.root():
                raise Problem('Initialize Git explicitly first.')
            paths = self.validate_paths(paths)
            if self.git('diff','--cached','--name-only','--',*paths).stdout:
                raise Problem('Selected files already contain staged changes. Commit or unstage them in your terminal first; Looking Glass will preserve them.')
            for state in ('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD'):
                if self.git('rev-parse','--verify',state,check=False).returncode == 0:
                    raise Problem('Finish the in-progress Git operation in your terminal first.')
            old = self.git('rev-parse','--verify','HEAD',check=False)
            parent = old.stdout.decode().strip() if old.returncode == 0 else None
            with tempfile.TemporaryDirectory() as temporary:
                env = {**os.environ, 'GIT_INDEX_FILE': str(Path(temporary)/'index')}
                self.git('read-tree', parent if parent else '--empty', env=env)
                self.git('add','--',*paths,env=env)
                tree = self.git('write-tree',env=env).stdout.decode().strip()
                if parent and tree == self.git('rev-parse','HEAD^{tree}').stdout.decode().strip():
                    raise Problem('The selected files have no changes to checkpoint.')
                args = ['commit-tree',tree]
                if parent:
                    args += ['-p',parent]
                commit = self.git(*args,'-m',message.strip(),env=env).stdout.decode().strip()
                self.git('update-ref','-m','Looking Glass checkpoint','HEAD',commit,parent or '0'*40)
                # Reset only selected index entries to the new commit. Unrelated
                # entries retain their previous staged content.
                self.git('reset','-q',commit,'--',*paths)
            return dict(commit=commit, message=message.strip(), paths=paths)
