import os
import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page, open_file
from test_images import pixels

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_paste_annotate_comment_rename_restore(workspace_page):
    root,page,url,ws=workspace_page
    (root/'notes.md').write_text('# Images\n\nPaste here.\n')
    page.goto(url);open_file(page,'notes.md')
    page.locator('#mode').select_option('source')
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.press('Enter')
    page.evaluate('''() => {const c=document.createElement('canvas');c.width=240;c.height=160;const ctx=c.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,240,160);c.toBlob(blob=>{const transfer=new DataTransfer();transfer.items.add(new File([blob],'Screenshot.png',{type:'image/png'}));document.querySelector('.cm-content').dispatchEvent(new ClipboardEvent('paste',{clipboardData:transfer,bubbles:true,cancelable:true}));});}''')
    expect(page.locator('.cm-content')).to_contain_text('.looking-glass/images/')
    page.keyboard.press('Control+s')
    page.locator('#mode').select_option('live')
    expect(page.get_by_role('button',name='Annotate image',exact=True)).to_be_visible()
    page.get_by_role('button',name='Annotate image',exact=True).click()
    canvas=page.locator('.image-editor canvas');expect(canvas).to_be_visible();box=canvas.bounding_box()
    page.mouse.move(box['x']+20,box['y']+20);page.mouse.down();page.mouse.move(box['x']+100,box['y']+70,steps=8);page.mouse.up()
    expect(page.get_by_role('button',name='Undo',exact=True)).to_be_enabled()
    page.get_by_role('button',name='Undo',exact=True).click();page.get_by_role('button',name='Redo',exact=True).click()
    page.get_by_role('button',name='Comment',exact=True).click();canvas.click(position={'x':60,'y':60})
    page.get_by_role('textbox',name='Comment on image').fill('Image discussion persists')
    page.get_by_role('button',name='Add comment',exact=True).click()
    expect(page.locator('.image-editor .image-comment-marker')).to_have_count(1)
    page.get_by_role('button',name='Save image',exact=True).click();expect(page.locator('.image-editor')).to_have_count(0)
    thread=ws.threads('notes.md')[0];identifier=thread['image_annotation']['image_id'];assert ws.images.get(identifier)['current']!=ws.images.get(identifier)['original']
    page.reload();open_file(page,'notes.md')
    expect(page.locator('.markdown-image .image-comment-marker')).to_have_count(1)
    page.locator('.image-comment-marker').click();expect(page.locator('.image-comment-box')).to_contain_text('Image discussion persists')
    page.get_by_role('textbox',name='Reply to image thread').fill('A reply');page.get_by_role('button',name='Reply',exact=True).first.click()
    expect(page.locator('.image-comment-box')).to_have_count(0)
    page.once('dialog',lambda d:d.accept('renamed.png'));page.locator('.markdown-image img').click(button='right')
    page.get_by_role('button',name='Annotate image',exact=True).click()
    page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Restore original',exact=True).click();expect(page.locator('.image-editor')).to_have_count(0)
    assert ws.images.get(identifier)['current']==ws.images.get(identifier)['original']
    assert ws.images.get(identifier)['name']=='renamed.png'
    assert len(ws.get_thread(thread['id'])['messages'])==2
    page.locator('#mode').select_option('preview');expect(page.locator('.markdown-image img')).to_be_visible()
    expect(page.locator('.image-thread-label')).to_contain_text('Image annotation')
    page.locator('.thread blockquote').first.click();expect(page.locator('#mode')).to_have_value('preview')

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('theme',['light','dark'])
def test_wiki_disk_image_and_saved_eraser(workspace_page,theme):
    root,page,url,ws=workspace_page
    (root/'photo.png').write_bytes(pixels());(root/'notes.md').write_text('# Disk image\n\n![[photo.png]]\n\nEnd.\n')
    page.goto(url);open_file(page,'notes.md')
    page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
    page.set_viewport_size({'width':850,'height':800})
    page.get_by_role('button',name='Annotate image',exact=True).click()
    canvas=page.locator('.image-editor canvas');expect(canvas).to_be_visible();page.screenshot(path='/tmp/lg-image-'+theme+'.png');canvas.click(position={'x':30,'y':30})
    page.get_by_role('button',name='Save image',exact=True).click();expect(page.locator('.image-editor')).to_have_count(0)
    assert (root/'photo.png').read_bytes()!=pixels()
    page.get_by_role('button',name='Annotate image',exact=True).click()
    page.get_by_role('button',name='Eraser',exact=True).click();canvas.click(position={'x':30,'y':30})
    page.get_by_role('button',name='Save image',exact=True).click();expect(page.locator('.image-editor')).to_have_count(0)
    from PIL import Image
    assert Image.open(root/'photo.png').getpixel((30,30))[:3]==(255,255,255)
    page.locator('#mode').select_option('preview');expect(page.locator('.markdown-image img')).to_be_visible()

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_jpeg_paste_survives_typing_and_tab_switch(workspace_page):
    import base64
    import io
    import json
    root,page,url,ws=workspace_page
    (root/'notes.md').write_text('Before\n');(root/'other.md').write_text('Other document')
    page.goto(url);open_file(page,'notes.md');page.locator('#mode').select_option('source')
    page.locator('.cm-content').click();page.keyboard.press('Control+End')
    paused=[];page.route('**/api/images',lambda route:paused.append(route))
    with page.expect_request('**/api/images'):
        page.evaluate('''encoded=>{const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));const transfer=new DataTransfer();transfer.items.add(new File([bytes],'photo.jpg',{type:'image/jpeg'}));document.querySelector('.cm-content').dispatchEvent(new ClipboardEvent('paste',{clipboardData:transfer,bubbles:true,cancelable:true}));}''',base64.b64encode(pixels('JPEG')).decode())
    page.keyboard.insert_text('Typed while uploading\n');open_file(page,'other.md')
    image=ws.images.add(io.BytesIO(pixels('JPEG')),'photo.jpg')
    paused[0].fulfill(status=201,content_type='application/json',body=json.dumps(image))
    page.wait_for_function('() => document.querySelector(".tab[data-path=\\"notes.md\\"]")?.textContent.includes("notes.md")')
    open_file(page,'notes.md');expect(page.locator('.cm-content')).to_contain_text(image['id'])
    expect(page.locator('.cm-content')).to_contain_text('Typed while uploading')
    page.keyboard.press('Control+s')
    assert (root/'other.md').read_text()=='Other document'
