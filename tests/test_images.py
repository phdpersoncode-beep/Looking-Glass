import io
import pytest
from PIL import Image
from looking_glass.app import create_app
from looking_glass.workspace import Workspace, Problem


def pixels(format='PNG', color='white'):
    output=io.BytesIO();Image.new('RGB',(100,80),color).save(output,format);return output.getvalue()


@pytest.mark.parametrize('format,name', [('PNG','Screenshot.png'),('JPEG','Photo.jpeg')])
def test_image_lifecycle_and_threads(tmp_path,format,name):
    app=create_app(tmp_path);ws=app.extensions['workspace'];client=app.test_client();headers={'X-Looking-Glass-Token':ws.token}
    original=pixels(format)
    image=client.post('/api/images',headers=headers,data={'file':(io.BytesIO(original),name)}).json
    duplicate=ws.images.add(io.BytesIO(original),name)
    assert image['id']!=duplicate['id'] and image['name'].startswith(name.split('.')[0])
    embed=f"![](.looking-glass/images/{image['id']}_{image['name']})"
    (tmp_path/'notes.md').write_text('🪞\n'+embed)
    data=dict(path='notes.md',start=2,end=2+len(embed),version=ws.read('notes.md')['version'],x=.25,y=.5,body='Check the label',author='User')
    thread=client.post(f"/api/images/{image['id']}/comments",headers=headers,json=data)
    assert thread.status_code==201,thread.json
    identifier=thread.json['id'];assert thread.json['associated_with_image']
    assert thread.json['image_annotation']['x']==.25
    edited=pixels(format,'red')
    saved=ws.images.update(image['id'],image['version'],raw=edited)
    with pytest.raises(Problem,match='changed'): ws.images.update(image['id'],image['version'],restore=True)
    renamed=ws.images.update(image['id'],saved['version'],name='new name.png')
    restarted=Workspace(tmp_path)
    assert restarted.images.get(image['id'])['current']==edited
    assert restarted.get_thread(identifier)['associated_with_image']
    assert restarted.query_threads(q='Check the label')['total']==1
    restored=restarted.images.update(image['id'],renamed['version'],restore=True)
    assert restarted.images.get(image['id'])['current']==original
    assert restarted.get_thread(identifier)['messages'][0]['body']=='Check the label'
    assert client.get(f"/api/images/{image['id']}/content").status_code==401
    assert client.get(f"/api/images/{image['id']}/content",headers=headers).data==original
    assert restored['version']!=renamed['version']


def test_invalid_images_and_coordinates(tmp_path):
    ws=Workspace(tmp_path)
    for raw in (b'not an image',b'\x89PNG\r\n\x1a\n'+b'x'*40,b'\xff\xd8\xffoops\xff\xd9'):
        with pytest.raises(Problem):ws.images.add(io.BytesIO(raw),'test.png')
    image=ws.images.add(io.BytesIO(pixels()),'test.png')
    for name in ('../bad.png','bad/name.png','bad\\name.png',''):
        with pytest.raises(Problem):ws.images.update(image['id'],image['version'],name=name)
    for coordinate in (-1,2,float('nan'),True,None):
        with pytest.raises(Problem):ws.images.comment(image['id'],dict(x=coordinate,y=.5))


def test_image_comment_review_and_removed_embed(tmp_path):
    ws=Workspace(tmp_path);image=ws.images.add(io.BytesIO(pixels()),'test.png')
    text=f"![[.looking-glass/images/{image['id']}_test.png]]"
    (tmp_path/'notes.md').write_text(text)
    review=ws.reviews.start('notes.md',ws.read('notes.md')['version'])
    thread=ws.images.comment(image['id'],dict(path='notes.md',review_id=review['id'],version=review['version'],start=0,end=len(text),x=0,y=1,body='Review comment',author='User'))
    assert not ws.threads('notes.md')
    assert thread['associated_with_image']
    ws.reviews.approve(review['id'],review['version'])
    assert ws.get_thread(thread['id'])['associated_with_image']
    (tmp_path/'notes.md').write_text('Removed image')
    assert ws.get_thread(thread['id'])['anchor_status']=='needs_reattachment'


def test_local_image_updates_rename_conflicts_and_restore(tmp_path):
    original=pixels();(tmp_path/'photo.png').write_bytes(original)
    ws=Workspace(tmp_path);image=ws.images.import_file('photo.png')
    assert ws.images.import_file('photo.png')['id']==image['id']
    assert (ws.images.directory/(image['id']+'_photo.png')).read_bytes()==original
    edited=pixels(color='red');image=ws.images.update(image['id'],image['version'],raw=edited)
    assert (tmp_path/'photo.png').read_bytes()==edited
    (tmp_path/'taken.png').write_bytes(original)
    with pytest.raises(Problem,match='already exists'):ws.images.update(image['id'],image['version'],name='taken.png')
    image=ws.images.update(image['id'],image['version'],name='renamed.png')
    assert not (tmp_path/'photo.png').exists()
    assert (tmp_path/'renamed.png').read_bytes()==edited
    assert ws.images.import_file('photo.png')['id']==image['id']
    image=ws.images.update(image['id'],image['version'],restore=True)
    assert (tmp_path/'renamed.png').read_bytes()==original
    (tmp_path/'renamed.png').write_bytes(pixels(color='blue'))
    with pytest.raises(Problem,match='external changes'):ws.images.update(image['id'],image['version'],raw=edited)
    assert (tmp_path/'renamed.png').read_bytes()==pixels(color='blue')


def test_local_image_comment(tmp_path):
    (tmp_path/'assets').mkdir();(tmp_path/'assets'/'photo.png').write_bytes(pixels())
    (tmp_path/'docs').mkdir();text='![[../assets/photo.png]]';(tmp_path/'docs'/'notes.md').write_text(text)
    ws=Workspace(tmp_path);image=ws.images.import_file('assets/photo.png')
    thread=ws.images.comment(image['id'],dict(path='docs/notes.md',version=ws.read('docs/notes.md')['version'],start=0,end=len(text),reference='../assets/photo.png',x=.5,y=.5,body='Disk comment',author='User'))
    assert thread['associated_with_image']


def test_external_replacement_retains_old_original_and_detaches_comments(tmp_path):
    (tmp_path/'photo.png').write_bytes(pixels())
    text='![[photo.png]]';(tmp_path/'notes.md').write_text(text)
    ws=Workspace(tmp_path);image=ws.images.import_file('photo.png')
    thread=ws.images.comment(image['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=0,end=len(text),reference='photo.png',x=.5,y=.5,body='Old geometry',author='User'))
    (tmp_path/'photo.png').write_bytes(pixels(color='blue'))
    replacement=ws.images.import_file('photo.png')
    assert replacement['id']!=image['id']
    assert ws.images.get(image['id'])['original']==pixels()
    assert ws.get_thread(thread['id'])['anchor_status']=='needs_reattachment'
    with pytest.raises(Problem,match='changed'):ws.images.update(image['id'],image['version'],restore=True)
    assert (tmp_path/'photo.png').read_bytes()==pixels(color='blue')
