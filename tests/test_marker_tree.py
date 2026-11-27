import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from looking_glass.app import create_app
from looking_glass.marker_tree import find_markers


def test_marker_syntax_and_locations():
    python = '''"""# TODO: a docstring"""
message = "#P1: a string"
emoji = "🪞"  #P0: Check escaped paths
# P1 : Follow up
##\tP2 Cache by file
#  P3
# TODO: Add help
#\tNOTE: Keep quiet
# P30: unrelated
# The TODO marker is mentioned in prose
'''.replace('\n', '\r\n')
    hits = list(find_markers('.py', python))
    assert [(hit['kind'], hit['line'], hit['text']) for hit in hits] == [
        ('P0', 3, 'Check escaped paths'), ('P1', 4, 'Follow up'),
        ('P2', 5, 'Cache by file'), ('P3', 6, ''),
        ('TODO', 7, 'Add help'), ('NOTE', 8, 'Keep quiet'),
    ]
    assert hits[0]['column'] == len('emoji = "🪞"  #'.encode('utf-16-le')) // 2

    markdown = '''# Overview
TODO: Write a guide
- [ ] #P0: Fix examples
1. # NOTE Show commands
Some prose <!-- #P1: inline --> <!--TODO: another-->
<!--
  P2: Review
-->
```python
# TODO: an example
```
Inline `<!-- TODO: a literal -->` and <!-- #P3: actual -->
`# TODO: inline code`
TODOist and NOTEBOOK are words
'''
    hits = list(find_markers('.markdown', markdown))
    assert [(hit['kind'], hit['line'], hit['text']) for hit in hits] == [
        ('TODO', 2, 'Write a guide'), ('P0', 3, 'Fix examples'), ('NOTE', 4, 'Show commands'),
        ('P1', 5, 'inline'), ('TODO', 5, 'another'), ('P2', 7, 'Review'), ('P3', 12, 'actual'),
    ]


def test_tree_reuses_reads_and_follows_workspace_discovery(tmp_path, monkeypatch):
    root = tmp_path/'workspace'
    root.mkdir()
    source = root/'source.PY'
    source.write_text('# TODO: First\n', encoding='utf-8')
    notes = root/'notes.md'
    notes.write_text('Ordinary text\n', encoding='utf-8')
    (root/'notes.txt').write_text('# TODO: Other extension', encoding='utf-8')
    (root/'config.yaml').write_text('# P0: Configuration', encoding='utf-8')
    (root/'data.json').write_text('{"data":"TODO"}', encoding='utf-8')
    (root/'helper.js').write_text('const literal = "// TODO: Skip"; // P2: Check this\n', encoding='utf-8')
    (root/'excluded').mkdir()
    (root/'excluded'/'hidden.md').write_text('TODO Hidden', encoding='utf-8')
    (root/'.looking.ignore').write_text('excluded/\n', encoding='utf-8')
    (root/'alias.py').symlink_to(source)
    app = create_app(root)
    ws = app.extensions['workspace']
    headers = {'X-Looking-Glass-Token': ws.token}
    read = ws.text
    calls = []

    def spy(path):
        if path != '.looking.ignore':
            calls.append(path)
        return read(path)

    monkeypatch.setattr(ws, 'text', spy)
    client = app.test_client()
    route = '/api/marker-tree'
    assert client.get(route).status_code == 401
    first = client.get(route, headers=headers)
    assert first.status_code == 200
    assert [file['path'] for file in first.json['files']] == ['helper.js', 'source.PY']
    assert calls == ['helper.js', 'notes.md', 'source.PY']
    assert ws.thread_index() == []

    conditional = {**headers, 'If-None-Match': first.headers['ETag']}
    calls.clear()
    unchanged = client.get(route, headers=conditional)
    assert unchanged.status_code == 304 and unchanged.data == b''
    assert calls == []

    before = source.stat()
    source.write_text('# TODO: Other\n', encoding='utf-8')
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    changed = client.get(route, headers=conditional)
    assert changed.json['files'][1]['markers'][0]['text'] == 'Other'
    assert calls == ['source.PY']

    source.rename(root/'renamed.py')
    notes.unlink()
    (root/'.looking.ignore').unlink()
    updated = client.get(route, headers=conditional)
    assert [file['path'] for file in updated.json['files']] == ['excluded/hidden.md', 'helper.js', 'renamed.py']


def test_marker_caps_and_workspace_switch(tmp_path, monkeypatch):
    monkeypatch.setattr('looking_glass.marker_tree.MAX_FILE_MARKERS', 3)
    monkeypatch.setattr('looking_glass.marker_tree.MAX_MARKERS', 4)
    first, second = tmp_path/'first', tmp_path/'second'
    first.mkdir()
    second.mkdir()
    (first/'a.md').write_text('TODO See this\n' * 5, encoding='utf-8')
    (first/'b.md').write_text('# NOTE See this too\n' * 2, encoding='utf-8')
    (second/'fresh.md').write_text('#P0 Fresh\n', encoding='utf-8')
    app = create_app(first)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    response = client.get('/api/marker-tree', headers=headers)
    assert response.json['count'] == 4
    assert response.json['truncated'] is True
    assert [len(file['markers']) for file in response.json['files']] == [3, 1]
    assert client.post('/api/workspace', headers=headers, json={'path': str(second)}).status_code == 200
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token, 'If-None-Match': response.headers['ETag']}
    updated = client.get('/api/marker-tree', headers=headers)
    assert updated.json['count'] == 1 and updated.json['truncated'] is False
    assert updated.json['files'][0]['path'] == 'fresh.md'
    assert client.get('/api/marker-tree?cached=1', headers=headers).json == updated.json


def test_restart_serves_cached_markers_while_refresh_checks_changes(tmp_path, monkeypatch):
    (tmp_path/'change.py').write_text('# TODO Before\n')
    (tmp_path/'remove.md').write_text('TODO Remove\n')
    (tmp_path/'same.md').write_text('# NOTE Keep\n')
    (tmp_path/'empty.md').write_text('No markers\n')
    route = '/api/marker-tree'
    app = create_app(tmp_path)
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    assert app.test_client().get(route + '?cached=1', headers=headers).status_code == 204
    first = app.test_client().get(route, headers=headers)

    (tmp_path/'change.py').write_text('# TODO After\n')
    (tmp_path/'remove.md').unlink()
    (tmp_path/'new.md').write_text('# P1 New\n')
    restarted = create_app(tmp_path)
    ws = restarted.extensions['workspace']
    listing, read = ws.file_listing, ws.text
    scanning, resume = Event(), Event()
    reads = []

    def held_listing():
        scanning.set()
        assert resume.wait(5)
        return listing()

    def record_read(path):
        reads.append(path)
        return read(path)

    monkeypatch.setattr(ws, 'file_listing', held_listing)
    monkeypatch.setattr(ws, 'text', record_read)
    conditional = {**headers, 'If-None-Match': first.headers['ETag']}
    with ThreadPoolExecutor() as executor:
        refresh = executor.submit(restarted.test_client().get, route, headers=conditional)
        try:
            assert scanning.wait(5)
            cached = restarted.test_client().get(route + '?cached=1', headers=headers)
            assert cached.json == first.json
            assert cached.headers['ETag'] == first.headers['ETag']
            assert reads == []
        finally:
            resume.set()
        updated = refresh.result()

    assert reads == ['change.py', 'new.md']
    assert updated.headers['ETag'] != first.headers['ETag']
    assert [entry['markers'][0]['text'] for entry in updated.json['files']] == ['After', 'New', 'Keep']
    assert restarted.test_client().get(route, headers={**headers, 'If-None-Match': updated.headers['ETag']}).status_code == 304


def test_corrupt_marker_cache_is_rebuilt(tmp_path):
    (tmp_path/'notes.md').write_text('TODO Recover\n')
    app = create_app(tmp_path)
    ws = app.extensions['workspace']
    cache = ws.meta/'marker-tree.json'
    cache.write_text('{"format":1,')
    headers = {'X-Looking-Glass-Token': ws.token}
    client = app.test_client()
    assert client.get('/api/marker-tree?cached=1', headers=headers).status_code == 204
    refreshed = client.get('/api/marker-tree', headers=headers)
    assert refreshed.json['count'] == 1
    assert create_app(tmp_path).test_client().get('/api/marker-tree?cached=1', headers=headers).json == refreshed.json


def test_notebook_scans_cell_source_and_ignores_outputs():
    notebook = {
        'cells': [
            {
                'outputs': [{'data': {'text/plain': '# NOTE Output with [braces] and "quotes"'}}],
                'source': [
                    'literal = "# P3 Not a Python comment"\n',
                    'emoji = "🪞"   #P0: Real code comment\r\n',
                    '# TO', 'DO: Split source fragment\n',
                ],
                'cell_type': 'code',
            },
            {'cell_type': 'raw', 'source': ['TODO Raw cell']},
            {'cell_type': 'markdown', 'source': 'Intro\nTODO: Explain setup\n<!-- # NOTE Inline -->\n'},
        ],
        'metadata': {'language_info': {'name': 'python'}, 'example': '#P1 Metadata'},
        'nbformat': 4,
    }
    for source in (json.dumps(notebook, indent=1, ensure_ascii=True),
                   json.dumps(notebook, ensure_ascii=False).replace('TODO: Explain', r'\u0054ODO: Explain')):
        hits = list(find_markers('.ipynb', source))
        assert [(h['kind'], h['cell'], h['line'], h['text']) for h in hits] == [
            ('P0', 1, 2, 'Real code comment'),
            ('TODO', 1, 3, 'Split source fragment'),
            ('TODO', 3, 2, 'Explain setup'),
            ('NOTE', 3, 3, 'Inline'),
        ]


def test_notebook_uses_kernel_language_ignores_unknown_code_and_handles_incomplete_json():
    notebook = {
        'metadata': {'kernelspec': {'language': 'javascript'}},
        'cells': [
            {'cell_type': 'code', 'source': 'const value = "// P1 literal";\n/* P1: Fix this */'},
            {'cell_type': 'markdown', 'source': ['TODO Explain value']},
        ],
    }
    assert [hit['text'] for hit in find_markers('.ipynb', json.dumps(notebook))] == ['Fix this', 'Explain value']
    notebook['metadata']['kernelspec']['language'] = 'unsupported'
    assert [hit['text'] for hit in find_markers('.ipynb', json.dumps(notebook))] == ['Explain value']
    assert list(find_markers('.ipynb', '{"cells":[{"source":"TODO Test"')) == []


def test_notebook_without_unescaped_candidate():
    content = r'{"cells":[{"cell_type":"markdown","source":"\u0054ODO: Start here"}]}'
    hit, = find_markers('.ipynb', content)
    assert hit['text'] == 'Start here'
    assert (hit['cell'], hit['line'], hit['column']) == (1, 1, 0)
