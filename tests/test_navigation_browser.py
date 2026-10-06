"""Explorer, Markdown contents, and JSONL navigation regressions."""
import os
import pytest
from test_requested_features import workspace_page, open_file

pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def test_explorer_toggle_preserves_width_folders_and_draft(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    (root/'folder').mkdir();(root/'folder'/'note.md').write_text('# Notes\n\nDraft.\n')
    page.goto(url);page.locator('#expand-files').click();open_file(page,'folder/note.md')
    separator=page.get_by_role('separator',name='Resize file explorer')
    separator.focus();page.keyboard.press('Home');page.keyboard.press('Shift+ArrowRight')
    expect(separator).to_have_attribute('aria-valuenow','170')
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('Unsaved')
    width=page.locator('.document-panel').bounding_box()['width']
    page.get_by_role('button',name='Hide file explorer',exact=True).click()
    expect(page.locator('.file-sidebar')).not_to_be_visible()
    expect(page.locator('#explorer-show')).to_be_focused()
    expect(page.locator('#tabs')).to_be_visible()
    assert page.locator('.document-panel').bounding_box()['width']>width
    expect(page.locator('.cm-content')).to_contain_text('Unsaved')
    page.locator('#zen-toggle').click();expect(page.locator('#explorer-show')).not_to_be_visible()
    page.locator('#zen-toggle').click();expect(page.locator('#explorer-show')).to_be_visible()
    page.get_by_role('button',name='Show file explorer',exact=True).click()
    expect(separator).to_have_attribute('aria-valuenow','170')
    expect(page.locator('.file-folder')).to_have_attribute('open','')
    expect(page.locator('.cm-content')).to_contain_text('Unsaved')
    page.locator('#save').click();expect(page.locator('#dirty')).to_have_text('')
    page.locator('#explorer-hide').click();page.reload()
    expect(page.locator('.file-sidebar')).not_to_be_visible()
    page.locator('#explorer-show').click();expect(separator).to_have_attribute('aria-valuenow','170')
    expect(page.locator('.file-folder')).to_have_attribute('open','')
    page.locator('#collapse-files').click();expect(page.locator('.file-folder')).not_to_have_attribute('open','')
    page.locator('#expand-files').click();expect(page.locator('.file-folder')).to_have_attribute('open','')
