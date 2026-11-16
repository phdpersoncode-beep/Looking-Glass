"""Creation, capped discovery, and zen shortcuts through actual browser interactions."""
import os
import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page,open_file

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def create(page,kind,name):
    page.get_by_role('button',name='New '+kind,exact=True).click()
    dialog=page.get_by_role('dialog',name='New '+kind,exact=True)
    dialog.get_by_role('textbox',name='Name',exact=True).fill(name)
    dialog.get_by_role('button',name='Create',exact=True).click()
    expect(dialog).to_have_count(0)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_create_empty_workspace_nested_entries_collision_and_dirty_tabs(workspace_page):
    root,page,url,ws=workspace_page
    page.goto(url)
    create(page,'folder','src')
    expect(page.locator('.file-folder[data-directory="src"]')).to_be_visible()
    create(page,'file','new 🪞.py')
    expect(page.locator('#document-name')).to_have_text('src/new 🪞.py')
    expect(page.locator('.cm-content')).to_be_focused()
    expect(page.locator('.file-entry[data-path="src/new 🪞.py"]')).to_be_visible()
    assert (root/'src/new 🪞.py').read_text()==''
    page.locator('.cm-content').click();page.keyboard.insert_text('unsaved = 42')
    # Folder actions choose that folder, and opening a new file retains the old draft.
    page.locator('.file-folder[data-directory="src"]>summary').click(button='right')
    page.get_by_role('menuitem',name='New file',exact=True).click()
    dialog=page.get_by_role('dialog',name='New file',exact=True)
    dialog.locator('input').fill('new 🪞.py');dialog.get_by_role('button',name='Create',exact=True).click()
    expect(dialog.locator('[role=alert]')).to_contain_text('already exists')
    dialog.locator('input').fill('other.py');dialog.get_by_role('button',name='Create',exact=True).click()
    expect(page.locator('#document-name')).to_have_text('src/other.py')
    open_file(page,'src/new 🪞.py');expect(page.locator('.cm-content')).to_have_text('unsaved = 42')
    page.locator('.cm-content').click();page.keyboard.press('Control+z');expect(page.locator('.cm-content')).to_have_text('')
    assert (root/'src/new 🪞.py').read_text()==''
    page.get_by_role('button',name='New folder',exact=True).click()
    dialog=page.get_by_role('dialog',name='New folder',exact=True)
    dialog.locator('input').fill('cancelled');dialog.get_by_role('button',name='Cancel',exact=True).click()
    assert not (root/'src/cancelled').exists()
    page.reload();expect(page.locator('.file-folder[data-directory="src"]')).to_be_visible()


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_warning_clears_after_ignore_edit_without_losing_draft(workspace_page,monkeypatch):
    import looking_glass.workspace as workspace
    monkeypatch.setattr(workspace,'FILE_LIMIT',3)
    root,page,url,ws=workspace_page
    (root/'a.txt').write_text('Original');(root/'.looking.ignore').write_text('')
    (root/'generated').mkdir()
    for i in range(3):(root/'generated'/f'{i}.txt').write_text('Generated')
    page.goto(url);warning=page.locator('.explorer-warning')
    expect(warning).to_contain_text('File limit reached (3)');expect(warning).to_contain_text('.looking.ignore')
    open_file(page,'a.txt');page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text(' draft')
    (root/'.looking.ignore').write_text('generated/\n');page.locator('#refresh-files').click()
    expect(warning).to_have_count(0);expect(page.locator('.cm-content')).to_have_text('Original draft')
    assert (root/'a.txt').read_text()=='Original'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_alt_z_in_editor_and_html_preserves_undo_and_legacy_shortcut(workspace_page):
    root,page,url,ws=workspace_page
    (root/'a.txt').write_text('Original');(root/'report.html').write_text('<p>Report</p>')
    page.goto(url);open_file(page,'a.txt')
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text(' draft')
    toggle=page.locator('#zen-toggle');page.keyboard.press('Alt+z');expect(toggle).to_have_attribute('aria-pressed','true')
    page.keyboard.press('Alt+z');expect(toggle).to_have_attribute('aria-pressed','false')
    page.keyboard.press('Control+z');expect(page.locator('.cm-content')).to_have_text('Original')
    page.keyboard.press('Control+Alt+z');expect(toggle).to_have_attribute('aria-pressed','true')
    page.keyboard.press('Alt+z');expect(toggle).to_have_attribute('aria-pressed','false')
    open_file(page,'report.html');page.frame_locator('#html-preview').locator('p').click()
    page.keyboard.press('Alt+z');expect(toggle).to_have_attribute('aria-pressed','true')
    page.keyboard.press('Alt+z');expect(toggle).to_have_attribute('aria-pressed','false')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_creation_controls_fit_themes_narrow_panes_and_root_context(workspace_page):
    root,page,url,ws=workspace_page
    (root/'src').mkdir();(root/'src/a.py').write_text('value = 1\n')
    page.goto(url);page.locator('.file-folder[data-directory="src"]>summary').click()
    for theme,width in [('light',1440),('dark',780)]:
        page.set_viewport_size({'width':width,'height':740})
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        page.locator('#file-resize').focus();page.keyboard.press('Home')
        sidebar=page.locator('#file-sidebar').bounding_box()
        for control in ['#new-file','#new-folder']:
            rect=page.locator(control).bounding_box()
            assert rect['x']>=sidebar['x'] and rect['x']+rect['width']<=sidebar['x']+sidebar['width']
        page.locator('#new-file').click();dialog=page.get_by_role('dialog',name='New file',exact=True)
        expect(dialog).to_contain_text('Create in src')
        rect=dialog.bounding_box();assert rect['x']>=0 and rect['x']+rect['width']<=width
        page.keyboard.press('Escape');expect(dialog).to_have_count(0)
    tree=page.locator('#file-tree');rect=tree.bounding_box()
    tree.click(button='right',position={'x':20,'y':rect['height']-10})
    page.get_by_role('menuitem',name='New folder',exact=True).click()
    dialog=page.get_by_role('dialog',name='New folder',exact=True)
    expect(dialog).to_contain_text('Create in workspace root')
    dialog.locator('input').fill('root-folder');dialog.get_by_role('button',name='Create',exact=True).click()
    expect(dialog).to_have_count(0)
    expect(page.locator('.file-folder[data-directory="root-folder"]')).to_be_visible()
    assert (root/'root-folder').is_dir() and not (root/'src/root-folder').exists()
