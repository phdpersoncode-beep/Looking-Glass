from urllib.parse import urlencode

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


def test_download_keeps_auth_and_file_path_contracts(tmp_path):
    (tmp_path/'report.html').write_text('<script>alert(1)</script>')
    (tmp_path/'note.txt').write_text('Plain text')
    (tmp_path/'link.html').symlink_to(tmp_path/'report.html')
    app = create_app(tmp_path)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    assert client.get('/api/download?path=report.html').status_code == 401
    assert client.get('/api/download?path=report.html', headers={**headers, 'Origin': 'null'}).status_code == 403
    for path, status in [('link.html', 403), ('../report.html', 403), ('.looking-glass/token', 403), ('missing.html', 404), ('note.txt', 400)]:
        assert client.get('/api/download?' + urlencode({'path': path}), headers=headers).status_code == status
