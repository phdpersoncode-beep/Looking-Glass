"""Read saved notebook cell source without retaining outputs."""
import io
import json
import re
from json.decoder import scanstring

WHITESPACE = re.compile(r'[ \t\r\n]*')
STRUCTURE = re.compile(r'["{}\[\]]')
STRING_END = re.compile(r'["\\]')
DECODER = json.JSONDecoder()


class NotebookJSON:
    """Walk known fields and skip big output values without building a JSON tree."""

    def __init__(self, text):
        self.text = text

    def skip_string(self, pos):
        while match := STRING_END.search(self.text, pos):
            if match[0] == '"':
                return match.end()
            pos = match.end() + 1  # Skip the escaped character.
        raise ValueError('Unclosed notebook JSON string.')

    def skip(self, start):
        text = self.text
        if text[start] == '"':
            return self.skip_string(start + 1)
        if text[start] not in '[{':
            return DECODER.raw_decode(text, start)[1]
        depth = 1
        pos = start + 1
        while match := STRUCTURE.search(text, pos):
            symbol = match[0]
            pos = match.end()
            if symbol == '"':
                pos = self.skip_string(pos)
            elif symbol in '[{':
                depth += 1
            else:
                depth -= 1
                if not depth:
                    return pos
        raise ValueError('Unclosed notebook JSON value.')

    def entries(self, start, opening):
        text = self.text
        start = WHITESPACE.match(text, start).end()
        if text[start:start + 1] != opening:
            return
        closing = '}' if opening == '{' else ']'
        pos = WHITESPACE.match(text, start + 1).end()
        while text[pos] != closing:
            key = None
            if opening == '{':
                if text[pos] != '"':
                    raise ValueError('Invalid notebook JSON key.')
                key, pos = scanstring(text, pos + 1)
                pos = WHITESPACE.match(text, pos).end()
                if text[pos] != ':':
                    raise ValueError('Missing notebook JSON colon.')
                pos = WHITESPACE.match(text, pos + 1).end()
            end = self.skip(pos)
            yield key, pos
            pos = WHITESPACE.match(text, end).end()
            if text[pos] == closing:
                break
            if text[pos] != ',':
                raise ValueError('Missing notebook JSON comma.')
            pos = WHITESPACE.match(text, pos + 1).end()

    def fields(self, start, names):
        if start is None:
            return {}
        return {key: pos for key, pos in self.entries(start, '{') if key in names}

    def string(self, start):
        if start is not None and self.text[start] == '"':
            return scanstring(self.text, start + 1)[0]
        return ''

    def strings(self, start):
        """Yield decoded fragments from string or array source."""
        if self.text[start] == '"':
            starts = (start,)
        else:
            starts = (pos for _, pos in self.entries(start, '['))
        for pos in starts:
            if self.text[pos] != '"':
                raise ValueError('Notebook source must contain strings.')
            yield scanstring(self.text, pos + 1)[0]


def notebook_sources(content):
    """Yield the notebook language and text of its Markdown and code cells."""
    reader = NotebookJSON(content)
    root = reader.fields(int(content.startswith('\ufeff')), {'cells', 'metadata'})
    if 'cells' not in root:
        return
    metadata = reader.fields(root.get('metadata'), {'language_info', 'kernelspec'})
    language = reader.fields(metadata.get('language_info'), {'name', 'file_extension'})
    kernel = reader.fields(metadata.get('kernelspec'), {'language'})
    name = (reader.string(language.get('name')) or reader.string(kernel.get('language'))).lower()
    extension = reader.string(language.get('file_extension')).lower()
    for number, (_, start) in enumerate(reader.entries(root['cells'], '['), 1):
        cell = reader.fields(start, {'cell_type', 'source'})
        kind = reader.string(cell.get('cell_type'))
        if kind in ('code', 'markdown') and 'source' in cell:
            source_at = cell['source']
            # Retain at most one cell's text at a time.
            with io.StringIO() as source:
                for value in reader.strings(source_at):
                    source.write(value)
                if source.tell():
                    yield number, kind, name, extension, source.getvalue()
