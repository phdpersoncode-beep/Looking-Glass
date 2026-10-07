import os
import pytest
from test_requested_features import workspace_page, open_file
from test_history import history_repo, git
pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER for browser checks')]

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
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

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
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
    expect(page.locator('#selection-tools')).not_to_be_visible()
    expect(page.locator('#save')).to_be_disabled();expect(page.locator('#annotate')).to_be_disabled()
    page.reload();expect(page.locator('#document-name')).to_have_text('Original · note.txt')
    (root/'note.txt').unlink();ws.get_thread(t['id'])
    page.locator('#thread-scope').check();page.locator('.jump').click()
    expect(page.locator('#document-name')).to_have_text('Original · note.txt')
    page.locator('.message-origin').click();expect(page.locator('.cm-content')).to_contain_text('Original passage.')
    page.locator('#reply-'+str(t['id'])).fill('Still discussable');page.locator('.reply-form button[type=submit]').click()
    expect(page.locator('.message p')).to_have_text(['Keep this discussion','Still discussable'])
    page.wait_for_timeout(2400)  # The next active-tab poll must stay quiet.
    expect(page.locator('#notice.error')).not_to_be_visible()

def paste_image(page,selector):
    page.locator(selector).evaluate('''el=>{
      const bytes=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII='),c=>c.charCodeAt(0));
      const file=new File([bytes],'image.png',{type:'image/png'}),data=new DataTransfer();data.items.add(file);
      const event=new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true});
      // Firefox constructs its own empty store instead of using the supplied one
      // (Mozilla bug 2027025). Populate the event's actual store before dispatch.
      if(!event.clipboardData.items.length)event.clipboardData.items.add(file);
      if(event.clipboardData.files.length!==1)throw new Error('Paste fixture has no image');
      el.dispatchEvent(event);
    }''')

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_clipboard_image_new_thread_reply_and_retry(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('A passage to discuss.')
    page.goto(url);open_file(page,'note.txt')
    page.locator('.cm-content').click();page.keyboard.press('Control+a')
    expect(page.locator('#annotate')).to_be_enabled();page.locator('#annotate').click()
    expect(page.locator('#comment-dialog')).to_be_visible()
    paperclip=page.get_by_role('button',name='Attach files to new thread',exact=True)
    expect(paperclip).to_be_visible()
    paste_image(page,'#comment-body');expect(page.locator('#comment-form .pending-file')).to_have_count(1)
    assert page.locator('#comment-form .pending-file img').evaluate('el=>el.src.startsWith("blob:")')
    page.locator('#comment-submit').click();expect(page.locator('.attachment')).to_have_count(1)
    t=ws.threads()[0];assert t['messages'][0]['body']==''
    assert t['attachments'][0]['message_id']==t['messages'][0]['id']
    paste_image(page,'#reply-'+str(t['id']))
    expect(page.locator('.reply-form .pending-file')).to_have_count(1)
    # A reply failure must retain both the text and screenshot for a safe retry.
    page.locator('#reply-'+str(t['id'])).fill('Screenshot feedback')
    page.route('**/api/threads/*/replies',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"Try again"}'))
    page.locator('.reply-form button[type=submit]').click();expect(page.locator('.composer-status.error')).to_have_text('Try again')
    expect(page.locator('.reply-form .pending-file')).to_have_count(1)
    expect(page.locator('#reply-'+str(t['id']))).to_have_value('Screenshot feedback')
    page.unroute('**/api/threads/*/replies');page.locator('.reply-form button[type=submit]').click()
    expect(page.locator('.attachment')).to_have_count(2);expect(page.locator('.pending-file')).to_have_count(0)
    assert len(ws.get_thread(t['id'])['messages'])==2
    # Ordinary text paste continues through the textarea's normal browser path.
    prevented=page.locator('#reply-'+str(t['id'])).evaluate('''el=>{
      const data=new DataTransfer();data.setData('text/plain','ordinary text');
      const event=new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true});
      if(!event.clipboardData.getData('text/plain'))event.clipboardData.setData('text/plain','ordinary text');
      if(event.clipboardData.getData('text/plain')!=='ordinary text')throw new Error('Paste fixture has no text');
      el.dispatchEvent(event);return event.defaultPrevented;
    }''')
    assert prevented is False
    page.reload();expect(page.locator('.attachment')).to_have_count(2)
    page.locator('.attachment-name').first.click();expect(page.locator('#attachment-image')).to_be_visible()


def test_history_commit_and_branch_discussions(workspace_page):
    from playwright.sync_api import expect
    from test_history import git
    root,page,url,ws=workspace_page
    history_repo.__wrapped__(root)
    sha=git(root,'rev-parse','agent/review')
    page.goto(url);page.locator('#history-open').click()
    page.locator('.commit-row',has_text='Agent review').click()
    page.locator('#history-comment').click();expect(page.locator('#selected-quote')).to_contain_text(sha[:8])
    page.locator('#comment-body').fill('Commit review');page.locator('#comment-submit').click()
    expect(page.locator('.thread .message p')).to_have_text('Commit review')
    t=ws.threads()[0];assert t['anchor_kind']=='commit' and t['commit_hash']==sha
    expect(page.locator('.commit-row',has_text='Agent review').locator('.history-discussion-count').first).to_be_visible()
    page.locator('#reply-'+str(t['id'])).fill('Commit reply');page.locator('.reply-form button[type=submit]').click()
    expect(page.locator('.thread .message p')).to_have_text(['Commit review','Commit reply'])
    page.locator('.original-context').click();expect(page.locator('.cm-content')).to_contain_text('Detailed review message')
    page.locator('#history-open').click()
    page.locator('.branch-badge[aria-label="Discuss branch agent/review"]').click()
    expect(page.locator('.thread')).to_have_count(0)
    page.locator('#history-comment').click();page.locator('#comment-body').fill('Branch review');page.locator('#comment-submit').click()
    expect(page.locator('.thread .message p')).to_have_text('Branch review')
    branch=ws.threads()[1];assert branch['git_target']['ref']=='refs/heads/agent/review'
    page.locator('.branch-filter summary').click()
    page.locator('.discuss-branch[aria-label="Discuss branch main"]').click()
    expect(page.locator('.history-target-bar')).to_contain_text('Branch main')
    expect(page.locator('.thread')).to_have_count(0)
    page.locator('.commit-row',has_text='Agent review').click()
    expect(page.locator('.thread .message p')).to_have_text(['Commit review','Commit reply'])
    page.reload();expect(page.locator('.thread .message p')).to_have_text(['Commit review','Commit reply'])
    page.locator('#thread-scope').check();expect(page.locator('.thread')).to_have_count(2)
    page.locator('.thread[data-thread="'+str(branch['id'])+'"] blockquote').click()
    expect(page.locator('.history-target-bar')).to_contain_text('Branch agent/review')
    expect(page.locator('#document-name')).to_have_text('Commit history')
    git(root,'branch','-D','agent/review')
    page.locator('.thread[data-thread="'+str(branch['id'])+'"] .original-context').click()
    expect(page.locator('.cm-content')).to_contain_text('Tip when reviewed: '+sha)
    page.locator('#reply-'+str(branch['id'])).fill('After deletion');page.locator('.thread[data-thread="'+str(branch['id'])+'"] .reply-form button[type=submit]').click()
    expect(page.locator('.thread[data-thread="'+str(branch['id'])+'"] .message p')).to_have_text(['Branch review','After deletion'])
