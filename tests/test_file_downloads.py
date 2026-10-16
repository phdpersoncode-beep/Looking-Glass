from urllib.parse import urlencode
from pathlib import Path

import pytest

from looking_glass.app import create_app
from looking_glass.workspace import MAX_TEXT


@pytest.mark.parametrize('suffix', ['html', 'HTM', 'jsonl'])
def test_download_bypasses_viewer_limit_and_preserves_bytes(tmp_path, suffix):
    name = f'report with spaces.{suffix}'
    raw = b'<p>\xc3\xbc</p>\r\n' + b' ' * MAX_TEXT
    (tmp_path/name).write_bytes(raw)
    app = create_app(tmp_path)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    query = urlencode({'path': name})
    assert client.get('/api/file?' + query, headers=headers).status_code == 413
    response = client.get('/api/download?' + query, headers=headers)
    assert response.status_code == 200
    assert response.data == raw
    assert response.headers['Content-Type'] == 'application/octet-stream'
    assert response.headers['Content-Disposition'].startswith('attachment;')
    assert name in response.headers['Content-Disposition']
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    url = client.post('/api/download', json={'path': name}, headers=headers).json['url']
    native = client.get(url)
    assert native.is_streamed
    assert native.data == raw
    assert native.headers['Content-Disposition'] == response.headers['Content-Disposition']
    assert app.extensions['workspace'].token not in url


def test_download_keeps_auth_and_file_path_contracts(tmp_path):
    (tmp_path/'report.html').write_text('<script>alert(1)</script>')
    (tmp_path/'note.txt').write_text('Plain text')
    (tmp_path/'link.html').symlink_to(tmp_path/'report.html')
    app = create_app(tmp_path)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    assert client.get('/api/download?path=report.html').status_code == 401
    assert client.post('/api/download', json={'path': 'report.html'}).status_code == 401
    assert client.get('/api/download?path=report.html', headers={**headers, 'Origin': 'null'}).status_code == 403
    assert client.post('/api/download', json={'path': 'report.html'}, headers={**headers, 'Origin': 'null'}).status_code == 403
    for path, status in [('link.html', 403), ('../report.html', 403), ('.looking-glass/token', 403), ('missing.html', 404), ('note.txt', 400)]:
        assert client.get('/api/download?' + urlencode({'path': path}), headers=headers).status_code == status
        assert client.post('/api/download', json={'path': path}, headers=headers).status_code == status


def test_native_download_is_file_scoped_expiring_and_supports_ranges(tmp_path, monkeypatch):
    (tmp_path/'report.html').write_bytes(b'0123456789')
    (tmp_path/'other.html').write_bytes(b'Other file')
    app = create_app(tmp_path)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    clock = [100.0]
    monkeypatch.setattr('looking_glass.app.time.monotonic', lambda: clock[0])
    url = client.post('/api/download', json={'path': 'report.html'}, headers=headers).json['url']
    assert client.get(url, headers={'Origin': 'null'}).status_code == 403
    assert client.get('/download/unknown').status_code == 404
    # A query parameter cannot change the file authorized by the capability.
    assert client.get(url+'?path=other.html').data == b'0123456789'
    # Native clients may request a range without sending the workspace API token.
    monkeypatch.setattr(Path, 'read_bytes', lambda self: pytest.fail('Do not read the whole download'))
    response = client.get(url, headers={'Range': 'bytes=2-5'})
    assert response.status_code == 206
    assert response.headers['Content-Range'] == 'bytes 2-5/10'
    assert response.data == b'2345'
    clock[0] += 60
    assert client.get(url).status_code == 404


def test_native_download_revalidates_paths_and_expires_on_workspace_switch(tmp_path):
    first, second = tmp_path/'first', tmp_path/'second'
    first.mkdir(); second.mkdir()
    (first/'report.html').write_text('First workspace')
    (second/'report.html').write_text('Second workspace')
    app = create_app(first)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    url = client.post('/api/download', json={'path': 'report.html'}, headers=headers).json['url']
    (first/'report.html').unlink()
    (first/'report.html').symlink_to(second/'report.html')
    assert client.get(url).status_code == 403
    (first/'report.html').unlink()
    (first/'report.html').write_text('First workspace')
    assert client.post('/api/workspace', json={'path': str(second)}, headers=headers).status_code == 200
    assert client.get(url).status_code == 404
