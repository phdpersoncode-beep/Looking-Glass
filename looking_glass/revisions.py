"""Explicit selected-path commits without staging unrelated work."""
import os
import subprocess
import tempfile
from pathlib import Path
from .workspace import Problem, MAX_TEXT


class Revisions:
    def __init__(self, workspace):
        self.ws = workspace

    def git(self, *args, env=None, check=True, timeout=None):
        environment = {**os.environ, **(env or {}), 'GIT_LITERAL_PATHSPECS':'1'}
        try:
            p = subprocess.run(['git', '-C', str(self.ws.root), *args], capture_output=True, env=environment, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise Problem('Git took too long. Try a smaller history selection.', 503) from error
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

    def history(self, branches=None, limit=100, offset=0, tips=None):
        """Bounded read-only history across local and fetched remote branches.

        Subsequent pages use the original tips so a concurrent commit cannot
        shift the offset and duplicate or drop rows.
        """
        limit = self.ws.query_integer(limit, 'Limit', 1, 200)
        offset = self.ws.query_integer(offset, 'Offset', 0, 100000)
        if not self.root():
            return dict(repository=False, branches=[], commits=[], tips=[], next_offset=None)
        raw = self.git('for-each-ref', '--format=%(refname)%00%(objectname)%00%(symref)',
                       'refs/heads', 'refs/remotes',timeout=15).stdout.decode('utf-8', errors='replace')
        refs = []
        for line in raw.splitlines():
            ref, sha, symbolic = line.split('\0')
            if not symbolic:
                refs.append(dict(ref=ref, name=ref.removeprefix('refs/heads/').removeprefix('refs/remotes/'), commit=sha))
        known = {r['ref']:r['commit'] for r in refs}
        if branches is not None and (not isinstance(branches, list) or any(b not in known for b in branches)):
            raise Problem('Choose branches from the repository branch list.')
        if tips is None:
            tips = list(dict.fromkeys(known[b] for b in branches)) if branches is not None else list(dict.fromkeys(known.values()))
            head = self.git('rev-parse', '--verify', 'HEAD', check=False)
            if branches is None and head.returncode == 0:
                tips = list(dict.fromkeys([head.stdout.decode().strip(), *tips]))
        else:
            import re
            if len(tips) > 1000 or any(not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', tip) for tip in tips):
                raise Problem('Invalid history cursor.')
        if not tips:
            return dict(repository=True, branches=refs, commits=[], tips=[], next_offset=None)
        # NUL fields handle multiline bodies, tabs, and unusual author names.
        fmt = '%H%x00%P%x00%an%x00%ae%x00%cn%x00%ce%x00%cI%x00%s%x00%B%x00'
        raw = self.git('log', '--date-order', f'--max-count={limit+1}', f'--skip={offset}',
                       f'--format={fmt}', *tips, '--',timeout=15).stdout.decode('utf-8', errors='replace')
        fields = raw.split('\0'); commits = []
        for i in range(0, len(fields)-1, 9):
            sha, parents, author, email, committer, committer_email, date, subject, message = fields[i:i+9]
            commits.append(dict(hash=sha.strip(), parents=parents.split(), author=author, author_email=email,
                                committer=committer, committer_email=committer_email, date=date,
                                subject=subject, message=message.rstrip()))
        return dict(repository=True, branches=refs, commits=commits[:limit], tips=tips,
                    next_offset=offset+limit if len(commits)>limit else None)

    def discussion_target(self, target):
        """Validate a history identity and snapshot its reviewed commit context."""
        import re
        if not isinstance(target, dict) or set(target) - {'kind','ref','commit_hash','label','path'}:
            raise Problem('Choose a commit or branch from the history viewer.')
        kind, ref = target.get('kind'), target.get('ref')
        if kind not in ('commit','branch') or not isinstance(ref,str):
            raise Problem('Choose a commit or branch from the history viewer.')
        root = self.root()
        if root is None:
            raise Problem('This workspace has no Git repository.')
        if kind == 'commit':
            if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',ref):
                raise Problem('Commit discussions require a full commit hash.')
            sha = ref
        else:
            raw = self.git('for-each-ref','--format=%(refname)%00%(objectname)%00%(symref)',
                           'refs/heads','refs/remotes',timeout=15).stdout.decode('utf-8',errors='replace')
            refs = {name:sha for name,sha,sym in (line.split('\0') for line in raw.splitlines()) if not sym}
            if ref not in refs:
                raise Problem('Choose an existing local or remote branch.',404)
            sha = refs[ref]
        if target.get('commit_hash') is not None and target['commit_hash'] != sha:
            raise Problem('The branch moved. Refresh history before starting this discussion.',409)
        if self.git('cat-file','-t',sha,check=False,timeout=15).stdout.strip() != b'commit':
            raise Problem('Commit not found.',404)
        context = self.git('show','-s','--format=%H%nCommitted by %cn <%ce>%nAuthored by %an <%ae>%n%cI%n%n%B',sha,'--',timeout=15).stdout.decode('utf-8',errors='replace').rstrip()
        subject = self.git('show','-s','--format=%s',sha,'--',timeout=15).stdout.decode('utf-8',errors='replace').strip()
        name = ref.removeprefix('refs/heads/').removeprefix('refs/remotes/')
        label = f'Commit {sha[:8]} · {subject}' if kind == 'commit' else f'Branch {name}'
        if kind == 'branch':
            context = f'{label}\n{ref}\nTip when reviewed: {sha}\n\n{context}'
        return dict(kind=kind,ref=ref,commit_hash=sha,label=label,path=f'looking-glass://git/{kind}/{ref}',
                    content=context,git_root=str(root))

    def baseline(self, path):
        """Read HEAD without touching the index, including outside open files."""
        file = self.ws.path(path)
        repository = self.git('-C',str(file.parent),'rev-parse','--show-toplevel',check=False)
        if repository.returncode:
            return dict(content=None)
        root = Path(repository.stdout.decode().strip())
        name = file.relative_to(root).as_posix()
        # Tracked files still get markers when a later ignore rule matches them.
        # check-ignore takes literal names and rejects GIT_LITERAL_PATHSPECS.
        ignored = self.git('-C',str(root),'--no-literal-pathspecs','check-ignore','--quiet','--',name,check=False)
        if ignored.returncode == 0:
            return dict(content=None)
        if ignored.returncode != 1:
            raise Problem(ignored.stderr.decode('utf-8', errors='replace').strip() or 'Cannot check Git ignore rules.')
        committed = self.git('-C',str(root),'show',f'HEAD:{name}',check=False)
        if committed.returncode:
            return dict(content='')
        if len(committed.stdout) > MAX_TEXT or b'\x00' in committed.stdout:
            return dict(content=None)
        try:
            return dict(content=committed.stdout.decode('utf-8'))
        except UnicodeDecodeError:
            return dict(content=None)

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
