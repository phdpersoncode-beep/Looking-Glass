import os
import pytest
from test_requested_features import workspace_page, open_file
from test_history import history_repo, git
pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER for browser checks')]

def test_history_tab_filter_and_draft(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    # Build the merge fixture in the same directory served by this browser.
    history_repo.__wrapped__(root)
    page.goto(url);open_file(page,'note.txt')
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.type(' draft')
    page.locator('#history-open').click();expect(page.locator('#document-name')).to_have_text('Commit history')
    expect(page.locator('.commit-row')).to_have_count(4)
    expect(page.locator('.commit-subject').first).to_have_text('Merge review')
    expect(page.locator('.commit-author',has_text='Codex')).to_have_count(1)
    assert 'Detailed review message' in page.locator('.commit-row',has_text='Agent review').get_attribute('title')
    page.locator('.commit-row',has_text='Agent review').click();expect(page.locator('.commit-detail')).to_contain_text('Detailed review message')
    page.locator('.branch-filter summary').click();page.get_by_role('checkbox',name='main',exact=True).uncheck()
    expect(page.locator('.commit-row')).to_have_count(2)
    expect(page.locator('.commit-subject').first).to_have_text('Agent review')
    page.locator('.tab-name',has_text='note.txt').click();expect(page.locator('.cm-content')).to_contain_text('draft')
    expect(page.locator('#dirty')).to_contain_text('Unsaved')
    assert (root/'note.txt').read_text()=='Original passage.\n'

def test_deleted_file_discussion_opens_original_context(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    history_repo.__wrapped__(root);f=ws.read('note.txt')
    t=ws.create_thread('note.txt',0,8,'Keep this discussion','Altay',f['version'])
    page.goto(url);open_file(page,'note.txt')
    page.locator('.original-context').click();expect(page.locator('#document-name')).to_have_text('Original · note.txt')
    expect(page.locator('.original-banner')).to_contain_text(t['commit_hash'][:8])
    expect(page.locator('.cm-content')).to_contain_text('Original passage.')
    assert page.locator('.cm-content').get_attribute('contenteditable')=='false'
    expect(page.locator('#save')).to_be_disabled();expect(page.locator('#annotate')).to_be_disabled()
    page.reload();expect(page.locator('#document-name')).to_have_text('Original · note.txt')
    (root/'note.txt').unlink();ws.get_thread(t['id'])
    page.locator('#thread-scope').check();page.locator('.jump').click()
    expect(page.locator('#document-name')).to_have_text('Original · note.txt')
    page.locator('.message-origin').click();expect(page.locator('.cm-content')).to_contain_text('Original passage.')
    page.locator('#reply-'+str(t['id'])).fill('Still discussable');page.locator('.reply-form button[type=submit]').click()
    expect(page.locator('.message p')).to_have_text(['Keep this discussion','Still discussable'])
