"""Shared Looking Glass dialogs, including image-adjacent attachment flows."""
import os
import pytest
from playwright.sync_api import expect
from test_requested_features import workspace_page,open_file
from test_images_browser import no_native_dialogs

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_attachment_popups_keep_values_and_cancel_without_changes(workspace_page):
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Discuss this.')
    thread=ws.create_thread('note.txt',0,7,'Review','User',ws.read('note.txt')['version'])
    page.goto(url);open_file(page,'note.txt');page.locator('.jump').click()
    page.locator('.reply-form .attach-files').set_input_files({'name':'draft.txt','mimeType':'text/plain','buffer':b'Attachment'})
    page.locator('.pending-file button').first.click()
    dialog=page.get_by_role('dialog',name='Rename attachment',exact=True)
    field=dialog.get_by_role('textbox',name='Name',exact=True)
    field.fill('../invalid');page.keyboard.press('Enter')
    expect(dialog.locator('[role=alert]')).to_contain_text('without slashes')
    expect(field).to_have_value('../invalid')
    field.fill('renamed.txt');page.keyboard.press('Enter')
    expect(page.locator('.pending-file')).to_contain_text('renamed.txt')
    page.locator('.reply-form button[type=submit]').click()
    expect(page.locator('.attachment')).to_have_count(1)
    page.get_by_label('Options for renamed.txt',exact=True).click()
    page.get_by_role('button',name='Remove renamed.txt',exact=True).click()
    deletion=page.get_by_role('dialog',name='Remove attachment?',exact=True)
    deletion.get_by_role('button',name='Cancel',exact=True).click()
    assert len(ws.get_thread(thread['id'])['attachments'])==1
    page.get_by_role('button',name='Remove renamed.txt',exact=True).click()
    deletion.get_by_role('button',name='Remove attachment',exact=True).click()
    expect(page.locator('.attachment')).to_have_count(0)


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_unsaved_tab_close_uses_themed_cancel_and_discard(workspace_page):
    root,page,url,_=workspace_page
    (root/'notes.md').write_text('Original text.')
    page.goto(url);open_file(page,'notes.md');page.locator('#mode').select_option('source')
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text(' Unsaved edit.')
    page.get_by_role('button',name='Close notes.md',exact=True).click()
    dialog=page.get_by_role('dialog',name='Discard unsaved edits?',exact=True)
    expect(dialog.get_by_role('button',name='Cancel',exact=True)).to_be_focused()
    page.keyboard.press('Escape');expect(page.locator('.cm-content')).to_contain_text('Unsaved edit.')
    page.get_by_role('button',name='Close notes.md',exact=True).click()
    dialog.get_by_role('button',name='Discard edits',exact=True).click()
    expect(page.locator('.tab')).to_have_count(0)
    assert (root/'notes.md').read_text()=='Original text.'
