import os
import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page, open_file
from test_images import pixels

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def clipboard_pixels():
    import io
    from PIL import Image
    stream=io.BytesIO();Image.new('RGB',(240,160),'white').save(stream,'PNG');return stream.getvalue()


def paste_clipboard_image(page,raw,name,media_type):
    import base64
    # Firefox's ClipboardEvent constructor ignores the clipboardData initializer
    # (Gecko ClipboardEvent.cpp). Supply the real DataTransfer on the instance;
    # the production event listener and all upload assertions remain unchanged.
    types=page.evaluate('''({encoded,name,media_type})=>{
      const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
      const transfer=new DataTransfer();transfer.items.add(new File([bytes],name,{type:media_type}));
      const event=new ClipboardEvent('paste',{bubbles:true,cancelable:true});
      Object.defineProperty(event,'clipboardData',{value:transfer});
      const types=[...event.clipboardData.items].map(item=>item.getAsFile()?.type);
      document.querySelector('.cm-content').dispatchEvent(event);return types;
    }''',dict(encoded=base64.b64encode(raw).decode(),name=name,media_type=media_type))
    assert types==[media_type]

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_paste_annotate_comment_rename_restore(workspace_page):
    root,page,url,ws=workspace_page
    (root/'notes.md').write_text('# Images\n\nPaste here.\n')
    page.goto(url);open_file(page,'notes.md')
    page.locator('#mode').select_option('source')
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.press('Enter')
    paste_clipboard_image(page,clipboard_pixels(),'Screenshot.png','image/png')
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
    page.locator('.markdown-image img').click(button='right')
    page.get_by_role('textbox',name='Name',exact=True).fill('renamed.png')
    page.get_by_role('button',name='Save name',exact=True).click()
    expect(page.locator('.lg-dialog')).to_have_count(0)
    page.get_by_role('button',name='Annotate image',exact=True).click()
    page.get_by_role('button',name='Restore original',exact=True).click();page.locator('.lg-dialog').get_by_role('button',name='Restore original',exact=True).click();expect(page.locator('.image-editor')).to_have_count(0)
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
        paste_clipboard_image(page,pixels('JPEG'),'photo.jpg','image/jpeg')
    page.keyboard.insert_text('Typed while uploading\n');open_file(page,'other.md')
    image=ws.images.add(io.BytesIO(pixels('JPEG')),'photo.jpg')
    paused[0].fulfill(status=201,content_type='application/json',body=json.dumps(image))
    page.wait_for_function('() => document.querySelector(".tab[data-path=\\"notes.md\\"]")?.textContent.includes("notes.md")')
    open_file(page,'notes.md');expect(page.locator('.cm-content')).to_contain_text(image['id'])
    expect(page.locator('.cm-content')).to_contain_text('Typed while uploading')
    page.keyboard.press('Control+s')
    assert (root/'other.md').read_text()=='Other document'

@pytest.fixture(autouse=True)
def no_native_dialogs(workspace_page):
    _,page,_,_=workspace_page
    native=[]
    def unexpected(dialog):
        native.append(dialog.type+': '+dialog.message)
        dialog.dismiss()
    page.on('dialog',unexpected)
    yield
    assert not native,native


def setup_disk_image(root,ws,name='photo.png',text=None):
    (root/name).write_bytes(pixels())
    text=text or f'# Image\n\n![]({name})\n\nEnd.\n'
    (root/'notes.md').write_text(text)
    return ws.images.import_file(name)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','preview'])
@pytest.mark.parametrize('work',['edit','review'])
def test_delete_exact_embed_cancel_undo_and_persistence(workspace_page,mode,work):
    root,page,url,ws=workspace_page
    original='# Images\n\n![First](photo.png)\n\nBetween.\n\n![Second](photo.png)\n\nEnd.\n'
    image=setup_disk_image(root,ws,text=original)
    start=original.index('![Second]')
    thread=ws.images.comment(image['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=start,end=start+len('![Second](photo.png)'),reference='photo.png',x=1,y=1,body='Keep this discussion',author='User'))
    page.goto(url);open_file(page,'notes.md')
    if work=='review':page.locator('#work-mode').click()
    page.locator('#mode').select_option(mode)
    delete=page.get_by_role('button',name='Delete image',exact=True)
    expect(delete).to_have_count(2)
    delete.last.click()
    confirmation=page.get_by_role('dialog',name='Delete image?',exact=True)
    expect(confirmation.get_by_role('button',name='Cancel')).to_be_focused()
    page.keyboard.press('Escape');expect(confirmation).to_have_count(0)
    expect(delete).to_have_count(2)
    delete.last.click();confirmation.get_by_role('button',name='Cancel').click();expect(delete).to_have_count(2)
    delete.last.click();confirmation.get_by_role('button',name='Delete image',exact=True).click()
    expect(page.locator('.markdown-image img[alt="First"]')).to_have_count(1)
    expect(page.locator('.markdown-image img[alt="Second"]')).to_have_count(0)
    page.locator('#mode').select_option('source');page.locator('.cm-content').click();page.keyboard.press('Control+z')
    expect(page.locator('.cm-content')).to_contain_text('![Second](photo.png)')
    page.locator('#mode').select_option(mode);expect(delete).to_have_count(2)
    delete.last.click();confirmation.get_by_role('button',name='Delete image',exact=True).click()
    if work=='edit':page.locator('#save').click()
    if work=='review':
        assert (root/'notes.md').read_text()==original
        page.locator('#approve-review').click();page.locator('#confirm-review-approve').click()
        expect(page.locator('#work-mode')).to_have_attribute('aria-checked','false')
    expect(page.locator('#dirty')).to_have_text('')
    assert (root/'notes.md').read_text()==original.replace('![Second](photo.png)','')
    assert (root/'photo.png').read_bytes()==pixels()
    assert ws.images.get(image['id'])['original']==pixels()
    assert ws.get_thread(thread['id'])['messages'][0]['body']=='Keep this discussion'
    assert ws.get_thread(thread['id'])['anchor_status']=='needs_reattachment'
    page.reload();open_file(page,'notes.md')
    expect(page.get_by_role('button',name='Delete image',exact=True)).to_have_count(1)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('theme,width,height,dimensions',[
    ('light',1440,960,(2400,1600)),('dark',850,700,(1200,2400)),
    ('light',500,700,(2400,1600)),('dark',500,700,(1200,2400))])
def test_annotation_layout_symbols_and_edge_markers(workspace_page,theme,width,height,dimensions):
    from PIL import Image
    root,page,url,ws=workspace_page
    Image.new('RGB',dimensions,'white').save(root/'photo.png')
    text='![](photo.png)';(root/'notes.md').write_text(text)
    image=ws.images.import_file('photo.png')
    for x,y in [(0,0),(1,1)]:
        ws.images.comment(image['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=0,end=len(text),reference='photo.png',x=x,y=y,body='Edge marker',author='User'))
    page.set_viewport_size({'width':width,'height':height});page.goto(url);open_file(page,'notes.md')
    page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
    pencil=page.get_by_role('button',name='Annotate image',exact=True)
    before=pencil.bounding_box();pencil.hover()
    assert pencil.bounding_box()==before
    assert pencil.locator('svg').count()==1
    pencil.click();editor=page.locator('.image-editor');expect(editor).to_be_visible()
    expect(editor.locator('.image-comment-marker')).to_have_count(2)
    assert editor.evaluate('(el,width)=>{const w=el.getBoundingClientRect().width;return w>width*.75&&w<=width-16;}',width)
    assert editor.locator('.image-toolbar button').evaluate_all("els=>els.every(el=>!el.textContent.trim()&&el.querySelector('svg')&&el.title&&el.getAttribute('aria-label'))")
    # The canvas, edge markers, and toolbar all fit inside the dialog.
    def fits():
        page.wait_for_function('''() => {const d=document.querySelector('.image-editor').getBoundingClientRect();return [...document.querySelectorAll('.image-editor canvas,.image-editor .image-comment-marker,.image-toolbar button')].every(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=d.left&&r.right<=d.right&&r.top>=d.top&&r.bottom<=d.bottom;});}''')
    fits()
    editor.locator('.image-comment-marker').last.click()
    expect(editor.get_by_role('textbox',name='Reply to image thread')).to_be_visible()
    fits()
    editor.get_by_role('textbox',name='Reply to image thread').fill('Reply from edge')
    page.keyboard.press('Meta+Enter')
    expect(editor.locator('.image-comment-box')).to_have_count(0)
    editor.get_by_role('button',name='Close',exact=True).click();expect(editor).to_have_count(0)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_comment_shortcut_errors_and_duplicate_submission(workspace_page):
    root,page,url,ws=workspace_page
    setup_disk_image(root,ws)
    page.goto(url);open_file(page,'notes.md');page.get_by_role('button',name='Annotate image',exact=True).click()
    page.get_by_role('button',name='Comment',exact=True).click();page.locator('.image-editor canvas').click()
    text=page.get_by_role('textbox',name='Comment on image')
    page.keyboard.press('Control+Enter')
    expect(page.locator('.image-comment-box [role=alert]')).to_have_text('Write a comment before sending.')
    text.fill('Keyboard');page.keyboard.press('Enter');page.keyboard.insert_text('comment')
    page.route('**/api/images/*/comments',lambda route:route.fulfill(status=409,json={'error':'Image changed. Try again.'}))
    page.keyboard.press('Control+Enter')
    expect(page.locator('.image-comment-box [role=alert]')).to_have_text('Image changed. Try again.')
    expect(text).to_have_value('Keyboard\ncomment')
    page.unroute('**/api/images/*/comments')
    held=[];page.route('**/api/images/*/comments',lambda route:held.append(route))
    with page.expect_request('**/api/images/*/comments'):page.keyboard.press('Control+Enter')
    page.keyboard.press('Control+Enter');expect(page.get_by_role('button',name='Add comment',exact=True)).to_be_disabled()
    assert len(held)==1
    held[0].continue_();expect(page.locator('.image-comment-box')).to_have_count(0)
    assert len(ws.threads('notes.md'))==1
    assert ws.threads('notes.md')[0]['messages'][0]['body']=='Keyboard\ncomment'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_rename_popup_validation_cancel_and_encoded_filename(workspace_page):
    root,page,url,ws=workspace_page
    image=setup_disk_image(root,ws,name='chart#1?.png',text='![](chart%231%3F.png)')
    (root/'taken.png').write_bytes(pixels(color='blue'))
    page.goto(url);open_file(page,'notes.md')
    expect(page.locator('.markdown-image img')).to_be_visible()
    page.locator('.markdown-image img').click(button='right')
    dialog=page.get_by_role('dialog',name='Rename image',exact=True);field=dialog.get_by_role('textbox',name='Name',exact=True)
    expect(field).to_have_value('chart#1?.png');field.fill('cancelled.png');page.keyboard.press('Escape')
    assert ws.images.get(image['id'])['name']=='chart#1?.png'
    page.locator('#mode').select_option('source');page.locator('.cm-line').filter(has_text='![](').click(button='right')
    expect(dialog).to_be_visible();field.fill('taken.png');page.keyboard.press('Enter')
    expect(dialog.locator('[role=alert]')).to_have_text('A file with that name already exists.')
    expect(field).to_have_value('taken.png');field.fill('renamed.png');page.keyboard.press('Enter')
    expect(dialog).to_have_count(0);expect(page.locator('.cm-content')).to_contain_text('![](renamed.png)')
    assert ws.images.get(image['id'])['name']=='renamed.png'
    assert (root/'renamed.png').read_bytes()==pixels()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_dirty_annotation_close_and_stale_save(workspace_page):
    root,page,url,ws=workspace_page
    image=setup_disk_image(root,ws)
    page.goto(url);open_file(page,'notes.md');page.get_by_role('button',name='Annotate image',exact=True).click()
    page.locator('.image-editor canvas').click()
    page.get_by_role('button',name='Close',exact=True).click()
    dialog=page.get_by_role('dialog',name='Discard annotations?',exact=True)
    dialog.get_by_role('button',name='Cancel').click();expect(page.locator('.image-editor')).to_be_visible()
    (root/'photo.png').write_bytes(pixels(color='blue'))
    page.get_by_role('button',name='Save image',exact=True).click()
    expect(page.locator('.image-editor [role=status]')).to_contain_text('external changes')
    assert (root/'photo.png').read_bytes()==pixels(color='blue')
    page.get_by_role('button',name='Close',exact=True).click();dialog.get_by_role('button',name='Discard annotations',exact=True).click()
    expect(page.locator('.image-editor')).to_have_count(0)
    assert ws.images.get(image['id'])['original']==pixels()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_delete_rejects_document_changed_during_confirmation(workspace_page):
    root,page,url,ws=workspace_page
    setup_disk_image(root,ws)
    page.goto(url);open_file(page,'notes.md')
    page.get_by_role('button',name='Delete image',exact=True).click()
    updated='External change.\n\n![](photo.png)\n'
    (root/'notes.md').write_text(updated)
    expect(page.locator('.cm-content')).to_contain_text('External change.',timeout=10000)
    page.locator('.lg-dialog').get_by_role('button',name='Delete image',exact=True).click()
    expect(page.get_by_role('status').filter(has_text='Document changed.')).to_be_visible()
    assert (root/'notes.md').read_text()==updated
    expect(page.get_by_role('button',name='Delete image',exact=True)).to_have_count(1)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_delete_last_managed_image_preserves_original_and_thread(workspace_page):
    import io
    root,page,url,ws=workspace_page
    image=ws.images.add(io.BytesIO(pixels()),'Screenshot.png')
    embed=f"![](.looking-glass/images/{image['id']}_{image['name']})"
    text='Before.\n\n'+embed+'\n\nAfter.\n';(root/'notes.md').write_text(text)
    thread=ws.images.comment(image['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=text.index(embed),end=text.index(embed)+len(embed),x=.5,y=.5,body='Retain original context',author='User'))
    page.goto(url);open_file(page,'notes.md');page.locator('#mode').select_option('preview')
    page.get_by_role('button',name='Delete image',exact=True).click()
    page.locator('.lg-dialog').get_by_role('button',name='Delete image',exact=True).click()
    expect(page.locator('.markdown-image')).to_have_count(0)
    page.locator('#save').click();expect(page.locator('#dirty')).to_have_text('')
    assert (root/'notes.md').read_text()==text.replace(embed,'')
    assert ws.images.get(image['id'])['original']==pixels()
    assert ws.get_thread(thread['id'])['anchor_status']=='needs_reattachment'
    page.reload();open_file(page,'notes.md')
    expect(page.locator('.markdown-image')).to_have_count(0)
    assert ws.get_thread(thread['id'])['messages'][0]['body']=='Retain original context'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('theme',['light','dark'])
def test_arrow_navigation_keeps_image_dom_and_explicit_source_edit(workspace_page,theme):
    root,page,url,ws=workspace_page
    setup_disk_image(root,ws,text='Before.\n\n![Image](photo.png)\n\nAfter.\n')
    page.goto(url);open_file(page,'notes.md');page.evaluate('(t)=>document.documentElement.dataset.theme=t',theme)
    expect(page.locator('.markdown-image img')).to_be_visible()
    page.evaluate('''()=>{window.heldImage=document.querySelector('.markdown-image');window.heldURL=window.heldImage.querySelector('img').src;window.imageChanges=0;window.imageObserver=new MutationObserver(records=>{for(const r of records)for(const n of r.removedNodes)if(n===window.heldImage||n.contains?.(window.heldImage))window.imageChanges++;});window.imageObserver.observe(document.querySelector('.cm-content'),{childList:true,subtree:true});}''')
    page.locator('.cm-content').click();page.keyboard.press('Control+Home')
    for _ in range(8):page.keyboard.press('ArrowDown')
    for _ in range(8):page.keyboard.press('ArrowUp')
    for _ in range(45):page.keyboard.press('ArrowRight')
    assert page.evaluate('window.heldImage===document.querySelector(".markdown-image")&&window.heldURL===window.heldImage.querySelector("img").src&&window.imageChanges===0')
    page.get_by_role('button',name='Edit image source',exact=True).click()
    expect(page.locator('.cm-content')).to_contain_text('![Image](photo.png)')
    expect(page.locator('.markdown-image')).to_have_count(0)
    page.get_by_role('button',name='Done editing image',exact=True).click()
    expect(page.locator('.markdown-image')).to_have_count(1)
    assert (root/'notes.md').read_text()=='Before.\n\n![Image](photo.png)\n\nAfter.\n'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','preview'])
@pytest.mark.parametrize('work',['edit','review'])
def test_centered_image_resize_persists_per_embed_and_undoes(workspace_page,mode,work):
    from PIL import Image
    root,page,url,ws=workspace_page
    Image.new('RGB',(600,400),'white').save(root/'photo.png')
    original='Before.\n\n![First](photo.png)\n\n![Second](photo.png)\n\nAfter.\n';(root/'notes.md').write_text(original)
    image_meta=ws.images.import_file('photo.png');start=original.index('![Second]')
    thread=ws.images.comment(image_meta['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=start,end=start+len('![Second](photo.png)'),reference='photo.png',x=.5,y=.5,body='Preserve through resize',author='User'))
    page.goto(url);open_file(page,'notes.md')
    if work=='review':page.locator('#work-mode').click()
    page.locator('#mode').select_option(mode)
    images=page.locator('.markdown-image');expect(images).to_have_count(2)
    image=images.last;expect(image.locator('img')).to_be_visible()
    container=page.locator('.cm-content' if mode=='live' else '.markdown-preview')
    box=image.bounding_box();area=container.bounding_box()
    assert abs(box['x']+box['width']/2-area['x']-area['width']/2)<3
    handle=image.get_by_role('slider',name='Resize image');handle.scroll_into_view_if_needed();rect=handle.bounding_box()
    page.mouse.move(rect['x']+12,rect['y']+12);page.mouse.down();page.mouse.move(rect['x']-48,rect['y']-28,steps=8);page.mouse.up()
    expect(image).to_have_css('width',f"{round(box['width']-120)}px")
    expect(image.locator('img')).to_be_visible()
    resized=image.locator('img').bounding_box();assert abs(resized['width']/resized['height']-1.5)<.02
    assert images.first.bounding_box()['width']==box['width']
    page.locator('#mode').select_option('source');expect(page.locator('.cm-content')).to_contain_text(f'![Second|{round(box["width"]-120)}](photo.png)')
    page.locator('.cm-content').click();page.keyboard.press('Control+z')
    expect(page.locator('.cm-content')).to_contain_text('![Second](photo.png)')
    page.keyboard.press('Control+Shift+z')
    if work=='review':
        assert (root/'notes.md').read_text()==original
        page.locator('#approve-review').click();page.locator('#confirm-review-approve').click()
    else:page.locator('#save').click()
    expect(page.locator('#dirty')).to_have_text('')
    assert f'![Second|{round(box["width"]-120)}](photo.png)' in (root/'notes.md').read_text()
    page.reload();open_file(page,'notes.md');page.locator('#mode').select_option(mode)
    expect(page.locator('.markdown-image').last).to_have_css('width',f"{round(box['width']-120)}px")
    assert Image.open(root/'photo.png').size==(600,400)
    assert ws.get_thread(thread['id'])['anchor_status']=='attached'
    assert ws.get_thread(thread['id'])['image_annotation']['x']==.5
    expect(page.locator('.markdown-image').last.locator('.image-comment-marker')).to_have_count(1)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','preview','editor'])
def test_ctrl_click_marker_drag_persists_and_cancels(workspace_page,mode):
    root,page,url,ws=workspace_page
    image=setup_disk_image(root,ws)
    text=(root/'notes.md').read_text();start=text.index('![');embed='![](photo.png)'
    thread=ws.images.comment(image['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=start,end=start+len(embed),reference='photo.png',x=.25,y=.3,body='Move this marker',author='User'))
    page.goto(url);open_file(page,'notes.md')
    if mode=='editor':page.get_by_role('button',name='Annotate image',exact=True).click()
    else:page.locator('#mode').select_option(mode)
    host=page.locator('.image-editor .image-stage' if mode=='editor' else '.image-pixels')
    marker=host.locator('.image-comment-marker');expect(marker).to_be_visible()
    marker.click(modifiers=['Control']);expect(marker).to_have_attribute('aria-pressed','true')
    expect(page.locator('.image-comment-box')).to_have_count(0)
    rect=host.bounding_box();b=marker.bounding_box();x=b['x']+b['width']/2;y=b['y']+b['height']/2
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(rect['x']+rect['width']*.75,rect['y']+rect['height']*.7,steps=8)
    with page.expect_response('**/api/images/*/comments/*'):
        page.mouse.up()
    expect(marker).to_have_css('left',f"{rect['width']*.75:g}px")
    page.wait_for_function('''()=>document.querySelector('.image-comment-marker')?.style.top==='70%' ''')
    moved=ws.get_thread(thread['id'])['image_annotation'];assert abs(moved['x']-.75)<.02 and abs(moved['y']-.7)<.02
    # A completed drop exits move mode; the next click opens the discussion.
    expect(marker).to_have_attribute('aria-pressed','false')
    marker.click();expect(page.locator('.image-comment-box')).to_contain_text('Move this marker')
    page.locator('.image-comment-box').get_by_role('button',name='Cancel',exact=True).click()
    # Escape abandons a second drag and exits move mode.
    marker.click(modifiers=['Control'])
    b=marker.bounding_box();page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2);page.mouse.down();page.mouse.move(rect['x']+5,rect['y']+5,steps=5)
    marker.press('Escape');page.mouse.up()
    expect(marker).to_have_attribute('aria-pressed','false')
    assert ws.get_thread(thread['id'])['image_annotation']==moved
    if mode=='editor':page.get_by_role('button',name='Close',exact=True).click()
    page.reload();open_file(page,'notes.md')
    restored=ws.get_thread(thread['id']);assert restored['image_annotation']==moved
    assert restored['messages'][0]['body']=='Move this marker'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('embed',['![Picture](photo.png)','![[photo.png]]'])
def test_image_resize_in_table_preserves_crlf_and_source_mapping(workspace_page,embed):
    root,page,url,ws=workspace_page
    (root/'photo.png').write_bytes(pixels())
    original='🪞 Before.\r\n\r\n| Picture | Value |\r\n| --- | --- |\r\n| '+embed+' | stays |\r\n'
    (root/'notes.md').write_bytes(original.encode())
    page.goto(url);open_file(page,'notes.md')
    handle=page.get_by_role('slider',name='Resize image');expect(handle).to_be_visible()
    handle.focus();handle.press('ArrowLeft')
    expect(page.locator('.markdown-image')).to_have_css('width','90px')
    expect(page.locator('.md-table td')).to_have_count(2)
    page.locator('#save').click();expect(page.locator('#dirty')).to_have_text('')
    saved=(root/'notes.md').read_bytes()
    assert b'\\|90' in saved and saved.count(b'\r\n')==original.count('\r\n')
    page.locator('#mode').select_option('preview')
    expect(page.locator('.markdown-image')).to_have_css('width','90px')
    expect(page.locator('.markdown-preview td')).to_have_count(2)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_svg_display_resize_keeps_bytes_and_renders_after_reopen(workspace_page):
    root,page,url,ws=workspace_page
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"><rect width="100" height="80"/></svg>'
    (root/'drawing.svg').write_text(svg);(root/'notes.md').write_text('![Drawing](drawing.svg)')
    page.goto(url);open_file(page,'notes.md')
    handle=page.get_by_role('slider',name='Resize image');expect(handle).to_be_visible()
    handle.focus();handle.press('ArrowLeft')
    expect(page.locator('.markdown-image')).to_have_css('width','90px')
    page.locator('#save').click();expect(page.locator('#dirty')).to_have_text('')
    assert (root/'notes.md').read_text()=='![Drawing|90](drawing.svg)'
    page.reload();open_file(page,'notes.md')
    expect(page.locator('.markdown-image')).to_have_css('width','90px')
    assert (root/'drawing.svg').read_text()==svg


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','preview','editor'])
def test_delete_image_comments_cancel_errors_last_comment_and_other_markers(workspace_page,mode):
    root,page,url,ws=workspace_page
    image=setup_disk_image(root,ws)
    text=(root/'notes.md').read_text();start=text.index('![')
    data=dict(path='notes.md',version=ws.read('notes.md')['version'],start=start,end=start+len('![](photo.png)'),reference='photo.png',x=.25,y=.3,body='First image comment',author='User')
    thread=ws.images.comment(image['id'],data)
    ws.reply(thread['id'],'Keep this reply','Agent')
    other=ws.images.comment(image['id'],{**data,'x':.8,'y':.8,'body':'Other marker stays'})
    page.goto(url);open_file(page,'notes.md')
    if mode=='editor':page.get_by_role('button',name='Annotate image',exact=True).click()
    else:page.locator('#mode').select_option(mode)
    host=page.locator('.image-editor .image-stage' if mode=='editor' else '.image-pixels')
    marker=host.locator(f'.image-comment-marker[data-thread="{thread["id"]}"]');marker.click()
    box=page.locator('.image-comment-box');draft=box.get_by_role('textbox',name='Reply to image thread');draft.fill('Unsent reply survives cancellation')
    deletion=box.get_by_role('button',name='Delete image comment',exact=True).first
    deletion.click();confirmation=page.get_by_role('dialog',name='Delete image comment?',exact=True)
    expect(confirmation.get_by_role('button',name='Cancel',exact=True)).to_be_focused()
    confirmation.get_by_role('button',name='Cancel',exact=True).click()
    expect(draft).to_have_value('Unsent reply survives cancellation')
    assert len(ws.get_thread(thread['id'])['messages'])==2
    # A failed deletion keeps the discussion and draft available for retry.
    endpoint=f'**/api/threads/{thread["id"]}/messages/*'
    page.route(endpoint,lambda route:route.fulfill(status=409,json={'error':'Please retry deletion.'}))
    deletion.click();confirmation.get_by_role('button',name='Delete comment',exact=True).click()
    expect(box.locator('[role=alert]')).to_have_text('Please retry deletion.')
    expect(draft).to_have_value('Unsent reply survives cancellation')
    page.unroute(endpoint)
    deletion.click();confirmation.get_by_role('button',name='Delete comment',exact=True).click()
    expect(box.locator('.image-comment-message')).to_have_count(1)
    expect(box).to_contain_text('Keep this reply');expect(box).not_to_contain_text('First image comment')
    expect(draft).to_have_value('Unsent reply survives cancellation')
    assert ws.get_thread(thread['id'])['messages'][0]['body']=='Keep this reply'
    expect(marker).to_have_count(1)
    box.get_by_role('button',name='Delete image comment',exact=True).click();confirmation.get_by_role('button',name='Delete comment',exact=True).click()
    expect(box).to_have_count(0);expect(marker).to_have_count(0)
    expect(host.locator('.image-comment-marker')).to_have_count(1)
    assert ws.get_thread(other['id'])['messages'][0]['body']=='Other marker stays'
    assert not any(t['id']==thread['id'] for t in ws.threads('notes.md'))
    with ws.connection() as db:assert db.execute('SELECT COUNT(*) FROM image_comments WHERE thread_id=?',(thread['id'],)).fetchone()[0]==0
    assert (root/'photo.png').read_bytes()==pixels() and (root/'notes.md').read_text()==text
    if mode=='editor':page.get_by_role('button',name='Close',exact=True).click()
    page.reload();open_file(page,'notes.md')
    expect(page.locator('.image-comment-marker')).to_have_count(1)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_delete_entire_image_thread_from_annotation_editor(workspace_page):
    root,page,url,ws=workspace_page
    image=setup_disk_image(root,ws);text=(root/'notes.md').read_text();start=text.index('![')
    thread=ws.images.comment(image['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=start,end=start+len('![](photo.png)'),reference='photo.png',x=.5,y=.5,body='Initial comment',author='User'))
    ws.reply(thread['id'],'A reply','Agent')
    page.goto(url);open_file(page,'notes.md');page.get_by_role('button',name='Annotate image',exact=True).click()
    page.locator('.image-editor .image-comment-marker').click()
    box=page.locator('.image-comment-box');box.get_by_role('button',name='Delete image thread',exact=True).click()
    dialog=page.get_by_role('dialog',name='Delete image thread?',exact=True);page.keyboard.press('Escape')
    expect(box).to_contain_text('Initial comment');expect(box).to_contain_text('A reply')
    box.get_by_role('button',name='Delete image thread',exact=True).click();dialog.get_by_role('button',name='Delete thread',exact=True).click()
    expect(box).to_have_count(0);expect(page.locator('.image-comment-marker')).to_have_count(0)
    assert not ws.threads('notes.md')
    assert ws.images.get(image['id'])['current']==pixels()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_discussion_image_previews_keep_controls_out_during_refresh(workspace_page):
    root,page,url,ws=workspace_page
    image=setup_disk_image(root,ws);text=(root/'notes.md').read_text();start=text.index('![')
    embed=f"![](.looking-glass/images/{image['id']}_{image['name']})"
    thread=ws.images.comment(image['id'],dict(path='notes.md',version=ws.read('notes.md')['version'],start=start,end=start+len('![](photo.png)'),reference='photo.png',x=.5,y=.5,body='Read this image.\n\n'+embed,author='User'))
    page.goto(url);open_file(page,'notes.md')
    preview=page.locator('.comment-markdown .markdown-image');expect(preview.locator('img')).to_be_visible()
    expect(preview.locator('button')).to_have_count(0)
    # A real discussion refresh must not add markers or editing controls to a preview.
    ws.reply(thread['id'],'Refresh this discussion','Agent')
    expect(page.locator('.comment-markdown').last).to_contain_text('Refresh this discussion',timeout=10000)
    expect(preview.locator('button')).to_have_count(0)
    expect(page.locator('#surface .image-comment-marker')).to_have_count(1)
