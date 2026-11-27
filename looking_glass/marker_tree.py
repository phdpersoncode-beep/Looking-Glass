"""Read-only index of saved markers in the workspace explorer."""
import io
import json
import os
import re
import secrets
import stat
from contextlib import suppress
from itertools import islice
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from .notebook_source import notebook_sources
from .source_comments import HASH, SUPPORTED as COMMENT_FILES, python_comments, source_comment_lines
from .workspace import MAX_TEXT, Problem

PYTHON = {'.py', '.pyi'}
MARKDOWN = {'.md', '.markdown'}
OTHER_SOURCE = COMMENT_FILES - PYTHON - MARKDOWN - {'.yaml', '.yml', '.toml'}
CODE = PYTHON | OTHER_SOURCE
PLAIN_SOURCES = CODE | MARKDOWN
SUPPORTED = PLAIN_SOURCES | {'.ipynb'}
NOTEBOOK_LANGUAGES = {
    'python': '.py', 'python2': '.py', 'python3': '.py', 'ipython': '.py',
    'javascript': '.js', 'typescript': '.ts', 'shell': '.sh', 'ruby': '.rb',
    'perl': '.pl', 'rust': '.rs', 'c++': '.cpp', 'c#': '.cs',
}
MAX_MARKERS = 5000
MAX_FILE_MARKERS = 1000
MAX_LABEL = 160
CACHE_FORMAT = 1

TAGS = r'(?:TODO|NOTE|P[0-3])'
PYTHON_CANDIDATE = re.compile(r'#[ \t]*' + TAGS + r'\b')
HASH_MARKER = re.compile(r'#[ \t#]*(' + TAGS + r')\b')
SOURCE_MARKER = re.compile(r'[ \t#/*<!-]*(' + TAGS + r')\b')
MARKDOWN_MARKER = re.compile(
    r'^[ \t]*(?:(?:[-+*]|\d{1,9}[.)])[ \t]+(?:\[[ xX]\][ \t]+)?)?'
    r'((?:#+[ \t]*' + TAGS + r')|TODO)\b'
)
COMMENT_MARKER = re.compile(r'[ \t#]*(' + TAGS + r')\b')
FENCE = re.compile(r'^[ ]{0,3}(`{3,}|~{3,})(.*)')
# Backtick spans on the same line take precedence over comment openers.
MARKDOWN_INLINE = re.compile(r'(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)|<!--')
NEWLINE = re.compile(r'\r\n?|\n')
CANDIDATE = re.compile(TAGS + r'\b')


def utf16_length(text):
    return len(text.encode('utf-16-le', errors='surrogatepass')) // 2


def marker(number, column, kind, tail):
    label = tail.lstrip(' \t:').rstrip()
    if len(label) > MAX_LABEL:
        label = label[:MAX_LABEL - 1] + '…'
    return dict(kind=kind, line=number, column=column, text=label)


class SourceCoordinates:
    """Translate increasing raw offsets into CodeMirror lines and UTF-16 columns."""

    def __init__(self, content):
        self.content = content
        self.breaks = NEWLINE.finditer(content)
        self.newline = next(self.breaks, None)
        self.line = 1
        self.column = self.previous = 0

    def locate(self, offset):
        while self.newline is not None and self.newline.end() <= offset:
            self.previous = self.newline.end()
            self.line += 1
            self.column = 0
            self.newline = next(self.breaks, None)
        self.column += utf16_length(self.content[self.previous:offset])
        self.previous = offset
        return self.line, self.column


def markdown_markers(content):
    fence = None
    in_comment = False
    for number, raw in enumerate(io.StringIO(content, newline=None), 1):
        line = raw.removesuffix('\n')
        if not in_comment:
            delimiter = FENCE.match(line)
            if fence:
                if (delimiter and delimiter[1].startswith(fence) and not delimiter[2].strip()):
                    fence = None
                continue
            if delimiter:
                fence = delimiter[1]
                continue

            match = MARKDOWN_MARKER.match(line)
            if match:
                kind = match[1].lstrip('# \t')
                yield marker(number, utf16_length(line[:match.end() - len(kind)]),
                             kind, line[match.end():])

        # An HTML comment can follow prose or span lines, with one marker per
        # line. Fences and inline code are never scanned as HTML comments.
        if not in_comment and '<!--' not in line:
            continue
        start = 0
        while start < len(line):
            if not in_comment:
                opening = MARKDOWN_INLINE.search(line, start)
                if not opening:
                    break
                start = opening.end()
                if opening[1]:
                    continue
            end = line.find('-->', start)
            match = COMMENT_MARKER.match(line, start, len(line) if end == -1 else end)
            if match:
                yield marker(number, utf16_length(line[:match.start(1)]), match[1],
                             line[match.end():] if end == -1 else line[match.end():end])
            in_comment = end == -1
            if in_comment:
                break
            start = end + 3


def other_source_markers(suffix, content):
    coordinates = SourceCoordinates(content)
    for start, line in source_comment_lines(suffix, content):
        match = SOURCE_MARKER.match(line)
        if match:
            number, column = coordinates.locate(start + match.start(1))
            tail = line[match.end():]
            if suffix in {'.html', '.htm'}:
                tail = tail.removesuffix('-->')
            elif suffix not in HASH:
                tail = tail.removesuffix('*/')
            yield marker(number, column, match[1], tail)


def notebook_markers(content):
    try:
        for number, kind, language, extension, source in notebook_sources(content):
            if kind == 'markdown':
                suffix = '.md'
            else:
                suffix = extension if extension in CODE else NOTEBOOK_LANGUAGES.get(
                    language, '.' + language if language else '.py')
                if suffix not in CODE:
                    continue
            for hit in find_markers(suffix, source):
                yield {**hit, 'cell': number}
    except (ValueError, IndexError):
        pass  # A notebook may be incomplete while another editor is saving it.


def find_markers(suffix, content):
    if suffix in PYTHON:
        last = None
        for last in PYTHON_CANDIDATE.finditer(content):
            pass
        if last is None:
            return
        # Lex from the start for string/comment context. After the last
        # possible hit, the remaining lines cannot contribute any markers.
        line_end = content.find('\n', last.end())
        if line_end != -1:
            content = content[:line_end + 1]
        if '\r' in content:
            content = content.replace('\r\n', '\n').replace('\r', '\n')
        for token in python_comments(content):
            match = HASH_MARKER.match(token.string)
            if match:
                yield marker(token.start[0], utf16_length(token.line[:token.start[1] + match.start(1)]),
                             match[1], token.string[match.end():])
    elif suffix == '.ipynb' and (CANDIDATE.search(content) or r'\u' in content):
        yield from notebook_markers(content)
    elif CANDIDATE.search(content):
        if suffix in MARKDOWN:
            yield from markdown_markers(content)
        elif suffix in OTHER_SOURCE:
            yield from other_source_markers(suffix, content)


class MarkerTree:
    def __init__(self, workspace):
        self.workspace = workspace
        self.cache_path = workspace.meta / 'marker-tree.json'
        self.scan_lock = Lock()
        self.load_lock = Lock()
        self.state = None

    def current(self):
        # Loading a saved snapshot never waits for workspace discovery.
        if self.state is None:
            with self.load_lock:
                if self.state is None:
                    self.state = self.load()
        return self.state

    def cached_snapshot(self):
        _, result, etag = self.current()
        return result, etag

    def load(self):
        try:
            if not self.cache_path.is_symlink():
                data = json.loads(self.cache_path.read_text(encoding='utf-8'))
                if data['format'] == CACHE_FORMAT:
                    cache = {path: (tuple(fingerprint), file, truncated)
                             for path, (fingerprint, file, truncated) in data['cache'].items()}
                    result, etag = data['result'], data['etag']
                    if (isinstance(result['files'], list) and type(result['count']) is int
                            and type(result['truncated']) is bool and isinstance(etag, str)
                            and re.fullmatch(r'[0-9a-f]{32}', etag)):
                        return cache, result, etag
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            pass  # The next refresh can rebuild a missing or damaged cache.
        return {}, None, None

    def persist(self, cache, result, etag):
        temporary = None
        try:
            with NamedTemporaryFile(dir=self.cache_path.parent, prefix='.marker-tree-',
                                    mode='w', encoding='utf-8', delete=False) as stream:
                temporary = stream.name
                json.dump(dict(format=CACHE_FORMAT, cache=cache, result=result, etag=etag),
                          stream, separators=(',', ':'))
            os.replace(temporary, self.cache_path)
        except OSError:
            # A cache write failure must not prevent serving freshly scanned markers.
            if temporary is not None:
                with suppress(OSError):
                    os.unlink(temporary)

    def snapshot(self):
        # Concurrent tree requests share the cache. The editor and discussions
        # use their own lock and can continue serving while this scan runs.
        with self.scan_lock:
            previous_cache, previous_result, etag = self.current()
            listing = self.workspace.file_listing()
            files, cache = [], {}
            count = 0
            truncated = listing['truncated']
            for path in listing['files']:
                suffix = Path(path).suffix.lower()
                if suffix not in SUPPORTED:
                    continue
                try:
                    fingerprint = self.fingerprint(path)
                    if fingerprint is None:
                        continue
                    entry = previous_cache.get(path)
                    if entry is None or entry[0] != fingerprint:
                        entry = self.read(path, suffix, fingerprint)
                    if entry is None:
                        continue
                except (OSError, Problem):
                    continue  # The working tree may be changing during discovery.

                cache[path] = entry
                _, file, file_truncated = entry
                truncated |= file_truncated
                if file is None:
                    continue
                remaining = MAX_MARKERS - count
                matches = file['markers']
                if len(matches) > remaining:
                    if remaining:
                        files.append({**file, 'markers': matches[:remaining]})
                    count = MAX_MARKERS
                    truncated = True
                    break
                files.append(file)
                count += len(matches)

            result = dict(files=files, count=count, truncated=truncated)
            if result != previous_result:
                etag = secrets.token_hex(16)
            if result != previous_result or cache != previous_cache:
                self.state = cache, result, etag
                self.persist(cache, result, etag)
            return result, etag

    def fingerprint(self, path):
        info = (self.workspace.root / path).lstat()
        if stat.S_ISREG(info.st_mode) and info.st_size <= MAX_TEXT:
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
        return None

    def read(self, path, suffix, fingerprint):
        try:
            content, version = self.workspace.text(path)
        except Problem as error:
            if error.status == 415:  # Binary or invalid UTF-8, until it changes.
                return fingerprint, None, False
            raise
        matches = list(islice(find_markers(suffix, content), MAX_FILE_MARKERS + 1))
        if fingerprint != self.fingerprint(path):
            return None
        file = dict(path=path, version=version, markers=matches[:MAX_FILE_MARKERS]) if matches else None
        return fingerprint, file, len(matches) > MAX_FILE_MARKERS
