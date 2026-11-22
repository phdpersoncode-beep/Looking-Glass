import os

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
    assert [file['path'] for file in first.json['files']] == ['source.PY']
    assert calls == ['notes.md', 'source.PY']
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
    assert changed.json['files'][0]['markers'][0]['text'] == 'Other'
    assert calls == ['source.PY']

    source.rename(root/'renamed.py')
    notes.unlink()
    (root/'.looking.ignore').unlink()
    updated = client.get(route, headers=conditional)
    assert [file['path'] for file in updated.json['files']] == ['excluded/hidden.md', 'renamed.py']


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
