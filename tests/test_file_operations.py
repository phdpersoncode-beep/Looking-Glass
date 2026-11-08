import pytest
from looking_glass.app import create_app
from looking_glass.workspace import Workspace,Problem
from looking_glass.file_operations import FileOperations


def test_move_directory_preserves_drafts_threads_origins_and_empty_dirs(tmp_path):
    (tmp_path/'src').mkdir();(tmp_path/'dest').mkdir();(tmp_path/'empty').mkdir()
    (tmp_path/'src'/'a.md').write_text('Reviewed passage.')
    ws=Workspace(tmp_path);thread=ws.create_thread('src/a.md',0,8,'Keep me','User',ws.read('src/a.md')['version'])
    review=ws.reviews.start('src/a.md',ws.read('src/a.md')['version'])
    op=FileOperations(ws);info=op.info('src');result=op.change('src',info['version'],'dest/src')
    assert result['destination']=='dest/src'
    restarted=Workspace(tmp_path)
    assert restarted.get_thread(thread['id'])['path']=='dest/src/a.md'
    assert restarted.reviews.read(review['id'])['path']=='dest/src/a.md'
    assert restarted.origins.read(thread['id'])['content']=='Reviewed passage.'
    assert 'empty' in ws.folders()
    assert ws.read('dest/src/a.md')['content']=='Reviewed passage.'


def test_operations_guard_stale_destinations_symlinks_and_trash(tmp_path):
    (tmp_path/'a.txt').write_text('old');(tmp_path/'b.txt').write_text('keep')
    ws=Workspace(tmp_path);op=FileOperations(ws);old=op.info('a.txt')
    (tmp_path/'a.txt').write_text('changed')
    with pytest.raises(Problem,match='changed'):op.change('a.txt',old['version'],'c.txt')
    current=op.info('a.txt')
    for path in ['../outside','/tmp/out','.looking-glass/moved','b.txt']:
        with pytest.raises(Problem):op.change('a.txt',current['version'],path)
    (tmp_path/'loop').symlink_to(tmp_path/'a.txt')
    with pytest.raises(Problem):op.info('loop')
    thread=ws.create_thread('a.txt',0,7,'History','User',ws.read('a.txt')['version'])
    op.change('a.txt',current['version'],delete=True)
    assert not (tmp_path/'a.txt').exists()
    assert next((ws.meta/'trash').rglob('a.txt')).read_text()=='changed'
    assert ws.get_thread(thread['id'])['messages'][0]['body']=='History'
    assert (tmp_path/'b.txt').read_text()=='keep'


def test_explorer_api_security_and_ignored_folders(tmp_path):
    (tmp_path/'a.txt').write_text('hello');(tmp_path/'visible').mkdir();(tmp_path/'ignored').mkdir()
    (tmp_path/'.looking.ignore').write_text('ignored/\n')
    app=create_app(tmp_path);ws=app.extensions['workspace'];client=app.test_client();headers={'X-Looking-Glass-Token':ws.token}
    assert client.get('/api/explorer?path=a.txt').status_code==401
    info=client.get('/api/explorer?path=a.txt',headers=headers).json
    assert client.post('/api/explorer',headers={**headers,'Origin':'https://evil.invalid'},json={**info,'destination':'renamed.txt'}).status_code==403
    assert client.post('/api/explorer',headers=headers,json={**info,'destination':'renamed.txt'}).status_code==200
    tree=client.get('/fragments/files',headers=headers).text
    assert 'data-directory="visible"' in tree and 'data-directory="ignored"' not in tree


def test_explorer_image_rename_updates_registration_and_rejects_stale_pixel_saves(tmp_path):
    from test_images import pixels
    (tmp_path/'photo.png').write_bytes(pixels());ws=Workspace(tmp_path);op=FileOperations(ws)
    image=ws.images.import_file('photo.png');info=op.info('photo.png');op.change('photo.png',info['version'],'renamed.png')
    with pytest.raises(Problem,match='changed'):ws.images.update(image['id'],image['version'],restore=True)
    current=ws.images.public(ws.images.get(image['id']));assert current['name']=='renamed.png'
    ws.images.update(image['id'],current['version'],raw=pixels(color='red'))
    assert (tmp_path/'renamed.png').read_bytes()==pixels(color='red')
    assert not (tmp_path/'photo.png').exists()


def test_moved_pending_review_can_be_edited_approved_and_bookmarks_survive(tmp_path):
    from test_pdfs import make_pdf
    (tmp_path/'src').mkdir();(tmp_path/'dest').mkdir()
    (tmp_path/'src/a.txt').write_text('Original')
    make_pdf(tmp_path/'src/paper.pdf');ws=Workspace(tmp_path);op=FileOperations(ws)
    pdf=ws.pdfs.read('src/paper.pdf');bookmarks=[{**pdf['bookmarks'][0],'title':'My bookmark ✓'}]
    ws.pdfs.save_bookmarks('src/paper.pdf',bookmarks,0,pdf['version'])
    review=ws.reviews.start('src/a.txt',ws.read('src/a.txt')['version'])
    thread=ws.reviews.create_thread(review['id'],review['version'],0,8,'Keep draft context','Agent')
    op.change('src',op.info('src')['version'],'dest/renamed')
    ws=Workspace(tmp_path)
    assert ws.pdfs.read('dest/renamed/paper.pdf')['bookmarks']==bookmarks
    assert ws.reviews.read(review['id'])['path']=='dest/renamed/a.txt'
    edited=ws.reviews.update(review['id'],review['version'],[dict(start=8,end=8,insert=' revised')],'Agent','agent')
    ws.reviews.approve(review['id'],edited['version'])
    assert (tmp_path/'dest/renamed/a.txt').read_text()=='Original revised'
    assert ws.get_thread(thread['id'])['path']=='dest/renamed/a.txt'
    assert ws.origins.read(thread['id'])['content']=='Original'
    assert not (tmp_path/'src').exists()


def test_folder_moves_refuse_stale_trees_protected_children_and_old_history(tmp_path):
    (tmp_path/'src').mkdir();(tmp_path/'src/a.txt').write_text('A')
    (tmp_path/'old.txt').write_text('Old discussion');ws=Workspace(tmp_path);op=FileOperations(ws)
    ws.create_thread('old.txt',0,3,'History','User',ws.read('old.txt')['version']);(tmp_path/'old.txt').unlink()
    with pytest.raises(Problem,match='existing review history'):
        op.change('src/a.txt',op.info('src/a.txt')['version'],'old.txt')
    assert (tmp_path/'src/a.txt').read_text()=='A'
    stale=op.info('src');(tmp_path/'src/new.txt').write_text('New')
    with pytest.raises(Problem,match='changed'):op.change('src',stale['version'],'moved')
    with pytest.raises(Problem,match='itself'):op.change('src',op.info('src')['version'],'src/child')
    (tmp_path/'src/.git').mkdir()
    with pytest.raises(Problem,match='protected'):op.info('src')
    (tmp_path/'src/.git').rmdir();(tmp_path/'src/link').symlink_to(tmp_path/'src/a.txt')
    with pytest.raises(Problem,match='symlinks'):op.info('src')
    for path in ['src/evil\x00.txt','src/evil\n.txt','src/link/new.txt']:
        with pytest.raises(Problem):op.change('src/a.txt',op.info('src/a.txt')['version'],path)


def test_metadata_error_rolls_back_disk_move_and_trash_manifest_cannot_clobber_payload(tmp_path):
    import json
    (tmp_path/'a.txt').write_text('A');(tmp_path/'restore.json').write_text('User data')
    ws=Workspace(tmp_path);op=FileOperations(ws)
    # A database failure after the filesystem rename must restore the source.
    with ws.connection() as db:
        db.execute("CREATE TRIGGER reject_move BEFORE UPDATE OF path ON snapshots BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    ws.read('a.txt')
    with pytest.raises(Exception,match='injected failure'):op.change('a.txt',op.info('a.txt')['version'],'b.txt')
    assert (tmp_path/'a.txt').read_text()=='A' and not (tmp_path/'b.txt').exists()
    op.change('restore.json',op.info('restore.json')['version'],delete=True)
    payload=next((ws.meta/'trash').glob('*/files/restore.json'))
    assert payload.read_text()=='User data'
    assert json.loads((payload.parent.parent/'restore.json').read_text())=={'path':'restore.json'}
