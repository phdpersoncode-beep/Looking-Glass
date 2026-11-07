import os
import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page,open_file
pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def menu(page,path):
    page.locator(f'.file-entry[data-path="{path}"]').click(button='right')
    return page.get_by_role('menu',name='File actions')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_explorer_rename_copy_delete_preserves_dirty_tabs_and_discussions(workspace_page):
    root,page,url,ws=workspace_page
    (root/'a.txt').write_text('Reviewed passage.');(root/'other.txt').write_text('Other')
    thread=ws.create_thread('a.txt',0,8,'Keep history','User',ws.read('a.txt')['version'])
    page.goto(url);open_file(page,'a.txt');page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text(' Draft')
    page.evaluate('''()=>{window.copied=[];navigator.clipboard.writeText=async text=>window.copied.push(text);}''')
    menu(page,'a.txt').get_by_role('menuitem',name='Copy relative path',exact=True).click()
    menu(page,'a.txt').get_by_role('menuitem',name='Copy absolute path',exact=True).click()
    assert page.evaluate('window.copied')==['a.txt',str(root/'a.txt')]
    menu(page,'a.txt').get_by_role('menuitem',name='Rename',exact=True).click()
    page.locator('.lg-dialog input').fill('renamed.txt');page.locator('.lg-dialog button[type=submit]').click()
    expect(page.locator('#document-name')).to_have_text('renamed.txt');expect(page.locator('.cm-content')).to_contain_text('Draft')
    page.keyboard.press('Control+s');expect(page.locator('#dirty')).to_have_text('')
    assert ws.get_thread(thread['id'])['path']=='renamed.txt'
    menu(page,'renamed.txt').get_by_role('menuitem',name='Delete',exact=True).click();page.locator('.lg-dialog').get_by_role('button',name='Cancel',exact=True).click()
    assert (root/'renamed.txt').exists()
    menu(page,'renamed.txt').get_by_role('menuitem',name='Delete',exact=True).click();page.locator('.lg-dialog button[type=submit]').click()
    expect(page.locator('.file-entry[data-path="renamed.txt"]')).to_have_count(0)
    assert next((root/'.looking-glass/trash').rglob('renamed.txt')).read_text().endswith(' Draft')
    assert ws.get_thread(thread['id'])['messages'][0]['body']=='Keep history'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_explorer_drag_folders_files_empty_targets_and_alt_q(workspace_page):
    root,page,url,ws=workspace_page
    (root/'src').mkdir();(root/'dest').mkdir();(root/'src/a.txt').write_text('A');(root/'b.txt').write_text('B')
    page.goto(url);page.locator('.file-folder[data-directory="src"]>summary').click();open_file(page,'src/a.txt')
    page.locator('.file-entry[data-path="src/a.txt"]').drag_to(page.locator('.file-folder[data-directory="dest"]>summary'))
    expect(page.locator('#document-name')).to_have_text('dest/a.txt')
    assert (root/'dest/a.txt').read_text()=='A'
    page.locator('.file-folder[data-directory="dest"]>summary').drag_to(page.locator('.file-folder[data-directory="src"]>summary'))
    expect(page.locator('#document-name')).to_have_text('src/dest/a.txt')
    assert (root/'src/dest/a.txt').exists()
    page.locator('.file-entry[data-path="src/dest/a.txt"]').drag_to(page.locator('.file-entry[data-path="b.txt"]'))
    expect(page.locator('#document-name')).to_have_text('a.txt');assert (root/'a.txt').exists()
    page.locator('.cm-content').click();page.keyboard.press('Alt+q')
    assert page.locator('.file-folder[open]').count()==0
    page.reload();assert page.locator('.file-folder[open]').count()==0


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_outline_individual_and_all_folds_keep_navigation(workspace_page):
    root,page,url,ws=workspace_page
    (root/'part.py').write_text('class Part:\n    def build(self):\n        def nested(): pass\n        return 1\n\ndef tail(): pass\n')
    page.goto(url);open_file(page,'part.py');page.locator('#code-outline>summary').click()
    outline=page.locator('#code-outline');toggle=outline.get_by_role('button',name='Toggle Part outline',exact=True)
    toggle.click();expect(outline.locator('.outline-name').filter(has_text='build')).not_to_be_visible()
    toggle.click();expect(outline.locator('.outline-name').filter(has_text='build')).to_be_visible()
    outline.get_by_role('button',name='Collapse all outline elements').click();expect(outline.locator('.outline-name').filter(has_text='build')).not_to_be_visible()
    outline.get_by_role('button',name='Expand all outline elements').click();expect(outline.locator('.outline-name').filter(has_text='nested')).to_be_visible()
    outline.get_by_role('button',name='method build, line 2',exact=True).click();expect(page.locator('.cm-activeLine')).to_contain_text('def build')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_file_mention_completion_ignore_rules_agent_references_and_navigation(workspace_page):
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Discuss this.');(root/'src').mkdir();(root/'src/part.py').write_text('VALUE=1');(root/'ignored.py').write_text('SECRET=1');(root/'.looking.ignore').write_text('ignored.py\n')
    thread=ws.create_thread('note.txt',0,7,'See @src/part.py and `@ignored.py`.','Agent',ws.read('note.txt')['version'])
    page.goto(url);open_file(page,'note.txt');page.locator('.jump').click()
    expect(page.locator('a[data-file-reference]')).to_have_count(1)
    reply=page.locator('.reply-form textarea');reply.fill('Please inspect @')
    popup=page.get_by_role('listbox',name='File references');expect(popup).to_be_visible();expect(popup).not_to_contain_text('ignored.py')
    reply.fill('Please inspect @spp');expect(popup.get_by_role('option')).to_have_text(['src/part.py'])
    reply.press('Enter');expect(reply).to_have_value('Please inspect @src/part.py ')
    reply.press('Control+Enter');expect(page.locator('a[data-file-reference]')).to_have_count(2)
    page.locator('a[data-file-reference]').first.click();expect(page.locator('#document-name')).to_have_text('src/part.py')
    assert ws.get_thread(thread['id'])['messages'][-1]['body']=='Please inspect @src/part.py'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_file_mentions_quoted_names_escape_dismiss_and_live_ignore_updates(workspace_page):
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Discuss this.');(root/'a space.md').write_text('Space');(root/'hidden.md').write_text('Hidden');(root/'.looking.ignore').write_text('hidden.md\n')
    page.goto(url);open_file(page,'note.txt');page.locator('.cm-content').click();page.keyboard.press('Control+a');page.locator('#annotate').click()
    field=page.locator('#comment-body');field.fill('Read @spa')
    popup=page.get_by_role('listbox',name='File references');expect(popup.get_by_role('option')).to_have_text(['a space.md'])
    field.press('Escape');expect(popup).to_have_count(0);expect(page.locator('#comment-dialog')).to_be_visible()
    field.fill('Read @spa');expect(popup).to_be_visible();field.press('Enter');expect(field).to_have_value('Read @"a space.md" ');chosen=field.input_value()
    (root/'.looking.ignore').write_text('hidden.md\na space.md\n')
    field.fill('Read @spa');expect(popup).to_have_text('No matching files')
    field.press('Escape');field.fill(chosen);page.locator('#comment-submit').click();expect(page.locator('a[data-file-reference]')).to_have_text('@"a space.md"')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_explorer_collision_and_unsaved_delete_are_visible_and_non_destructive(workspace_page):
    root,page,url,ws=workspace_page
    (root/'a.txt').write_text('A');(root/'b.txt').write_text('B')
    page.goto(url);open_file(page,'a.txt');page.locator('.cm-content').click();page.keyboard.insert_text('Draft')
    menu(page,'a.txt').get_by_role('menuitem',name='Rename',exact=True).click()
    dialog=page.locator('.lg-dialog');dialog.locator('input').fill('b.txt');dialog.locator('button[type=submit]').click()
    expect(dialog.locator('[role=alert]')).to_contain_text('already exists')
    expect(dialog.locator('input')).to_have_value('b.txt');dialog.get_by_role('button',name='Cancel').click()
    menu(page,'a.txt').get_by_role('menuitem',name='Delete',exact=True).click();page.locator('.lg-dialog button[type=submit]').click()
    expect(page.locator('#notice')).to_contain_text('Save or close unsaved files')
    assert (root/'a.txt').read_text()=='A' and (root/'b.txt').read_text()=='B'
    expect(page.locator('.cm-content')).to_contain_text('Draft')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_alt_q_from_html_and_outline_folds_survive_reopen(workspace_page):
    root,page,url,ws=workspace_page
    (root/'src').mkdir();(root/'src/part.py').write_text('class Part:\n    def build(self): pass\n');(root/'report.html').write_text('<p>Report text</p>')
    page.goto(url);page.locator('.file-folder>summary').click();open_file(page,'src/part.py');page.locator('#code-outline>summary').click()
    page.get_by_role('button',name='Toggle Part outline',exact=True).click()
    open_file(page,'report.html');page.frame_locator('#html-preview').locator('p').click();page.keyboard.press('Alt+q')
    expect(page.locator('.file-folder[open]')).to_have_count(0)
    page.locator('.file-folder>summary').click();open_file(page,'src/part.py')
    expect(page.locator('.outline-name').filter(has_text='build')).not_to_be_visible()
    expect(page.get_by_role('button',name='Toggle Part outline',exact=True)).to_have_attribute('aria-expanded','false')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_navigation_waits_for_move_and_draft_undo_survives(workspace_page):
    root,page,url,ws=workspace_page
    (root/'dest').mkdir();(root/'a.txt').write_text('Original');(root/'other.txt').write_text('Other')
    page.goto(url);open_file(page,'a.txt');page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text(' Draft')
    held=[]
    def delay(route):
        if route.request.method=='POST':held.append(route)
        else:route.continue_()
    page.route('**/api/explorer',delay)
    page.locator('.file-entry[data-path="a.txt"]').drag_to(page.locator('.file-folder>summary'))
    # The pending operation keeps the current text readable; a new visit waits.
    page.wait_for_function('()=>document.querySelector(".cm-content")?.getAttribute("aria-readonly")==="true"')
    page.locator('.file-entry[data-path="other.txt"]').click()
    expect(page.locator('#document-name')).to_have_text('a.txt')
    assert held;held[0].continue_()
    expect(page.locator('#document-name')).to_have_text('other.txt')
    open_file(page,'dest/a.txt');expect(page.locator('.cm-content')).to_contain_text('Original Draft')
    page.locator('.cm-content').click();page.keyboard.press('Control+z');expect(page.locator('.cm-content')).to_have_text('Original')
    assert (root/'dest/a.txt').read_text()=='Original'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_explorer_popups_and_folded_outline_fit_themes_and_narrow_windows(workspace_page):
    root,page,url,ws=workspace_page
    (root/'part.py').write_text('class Part:\n    def build(self):\n        def nested(): pass\n')
    page.goto(url);open_file(page,'part.py');page.locator('#code-outline>summary').click()
    for theme,width in [('light',1440),('dark',780)]:
        page.set_viewport_size({'width':width,'height':740})
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.get_by_role('button',name='Collapse all outline elements').click()
        expect(page.locator('.outline-name').filter(has_text='build')).not_to_be_visible()
        page.get_by_role('button',name='Expand all outline elements').click()
        expect(page.locator('.outline-name').filter(has_text='nested')).to_be_visible()
        menu(page,'part.py');popup=page.get_by_role('menu',name='File actions');box=popup.bounding_box()
        assert 0<=box['x'] and box['x']+box['width']<=width
        assert 0<=box['y'] and box['y']+box['height']<=740
        page.keyboard.press('Escape');expect(popup).to_have_count(0)
        page.locator('#code-outline>summary').click()
        page.locator('.cm-content').click();page.keyboard.press('Control+a');page.locator('#annotate').click()
        field=page.locator('#comment-body');field.fill('Read @part')
        mentions=page.get_by_role('listbox',name='File references');expect(mentions.get_by_role('option')).to_have_text(['part.py'])
        box=mentions.bounding_box()
        assert 0<=box['x'] and box['x']+box['width']<=width
        assert 0<=box['y'] and box['y']+box['height']<=740
        field.press('Enter');expect(field).to_have_value('Read @part.py ')
        page.locator('#comment-cancel').click();page.locator('#code-outline>summary').click()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_active_image_pdf_and_jsonl_viewers_remount_after_rename(workspace_page):
    from test_images import pixels
    from test_pdfs import make_pdf
    root,page,url,ws=workspace_page
    (root/'photo.png').write_bytes(pixels());make_pdf(root/'paper.pdf')
    (root/'rows.jsonl').write_text('{"hello":"World"}\n')
    page.goto(url)
    for source,target,visible in [('photo.png','renamed.png','.image-view img'),('paper.pdf','renamed.pdf','.pdf-page[data-ready=true]'),('rows.jsonl','renamed.jsonl','.jsonl-split')]:
        open_file(page,source);expect(page.locator(visible).first).to_be_visible()
        menu(page,source).get_by_role('menuitem',name='Rename',exact=True).click()
        page.locator('.lg-dialog input').fill(target);page.locator('.lg-dialog button[type=submit]').click()
        expect(page.locator('#document-name')).to_have_text(target)
        expect(page.locator(visible).first).to_be_visible()
        if source!='rows.jsonl':expect(page.locator('.cm-content')).to_have_count(0)
        assert (root/target).is_file() and not (root/source).exists()
