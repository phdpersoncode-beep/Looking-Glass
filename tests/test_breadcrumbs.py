from looking_glass.app import create_app


def test_breadcrumb_listing_is_shallow_and_uses_workspace_discovery(tmp_path):
    root = tmp_path/'project'
    root.mkdir()
    (root/'src'/'nested').mkdir(parents=True)
    (root/'src'/'nested'/'deep.py').write_text('value = 1')
    (root/'src'/'a.py').touch()
    (root/'src'/'Z.py').touch()
    (root/'src'/'hidden.py').touch()
    (root/'src'/'ignored').mkdir()
    (root/'src'/'.git').mkdir()
    (root/'src'/'alias').symlink_to(root/'src'/'nested')
    (root/'src'/'alias.py').symlink_to(root/'src'/'a.py')
    (root/'.looking.ignore').write_text('hidden.py\nignored/\n')
    app = create_app(root)
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}

    def browse(directory, *, authorized=True):
        return client.get('/api/workspace/children', query_string={'directory': directory},
                          headers=headers if authorized else {})

    assert browse('src', authorized=False).status_code == 401
    assert browse('src').json == {'truncated': False, 'entries': [
        {'name': 'nested', 'path': 'src/nested', 'directory': True},
        {'name': 'a.py', 'path': 'src/a.py', 'directory': False},
        {'name': 'Z.py', 'path': 'src/Z.py', 'directory': False},
    ]}
    assert [entry['path'] for entry in browse('').json['entries']] == ['src', '.looking.ignore']
    assert browse('src/nested').json['entries'][0]['path'] == 'src/nested/deep.py'
    for directory in ('src/ignored', 'src/alias', 'src/a.py', 'missing'):
        assert browse(directory).status_code == 404
    for directory in (str(tmp_path), '../', 'src/../src', 'src/.git'):
        assert browse(directory).status_code == 403


def test_breadcrumb_listing_reports_limit(tmp_path, monkeypatch):
    monkeypatch.setattr('looking_glass.workspace.FILE_LIMIT', 2)
    app = create_app(tmp_path)
    for name in ('a', 'b'):
        (tmp_path/name).touch()
    client = app.test_client()
    headers = {'X-Looking-Glass-Token': app.extensions['workspace'].token}
    response = client.get('/api/workspace/children', headers=headers)
    assert not response.json['truncated']
    (tmp_path/'c').touch()
    response = client.get('/api/workspace/children', headers=headers)
    assert response.json['truncated']
    assert len(response.json['entries']) == 2
