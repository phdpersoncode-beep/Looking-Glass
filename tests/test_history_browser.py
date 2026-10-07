import os
import pytest
from test_requested_features import workspace_page, open_file
from test_history import history_repo, git
pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER for browser checks')]

@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_history_layout_with_many_branch_labels(workspace_page):
    from playwright.sync_api import expect
    root,page,url,_=workspace_page
    history_repo.__wrapped__(root)
    for i in range(12):
        git(root,'branch',f'feature/long-review-branch-name-{i}')
    git(root,'update-ref','refs/remotes/origin/review',git(root,'rev-parse','agent/review'))
    page.goto(url);page.locator('#history-open').click()
    expect(page.locator('.commit-row')).to_have_count(4)

    def assert_layout():
        measurements=page.locator('.commit-row').evaluate_all('''rows=>rows.map(row=>{
            const box=selector=>row.querySelector(selector).getBoundingClientRect();
            const r=row.getBoundingClientRect(),graph=box('.commit-select>svg'),
                  content=box('.commit-content'),meta=box('.commit-meta'),badges=box('.branch-badges');
            return {textWidth:content.width,textAfterGraph:content.left>=graph.right,
                    badgesAfterText:!badges.width || badges.left>=content.right,
                    metaInside:meta.top>=r.top && meta.bottom<=r.bottom,
                    badgesInside:!badges.height || (badges.top>=r.top && badges.bottom<=r.bottom),
                    graphWidth:graph.width,expectedGraphWidth:Number(row.querySelector('.commit-select>svg').getAttribute('width'))};
        })''')
        for m in measurements:
            assert m['textWidth']>=200,m
            assert m['textAfterGraph'] and m['badgesAfterText'],m
            assert m['metaInside'] and m['badgesInside'],m
            assert m['graphWidth']==m['expectedGraphWidth'],m

    assert_layout()
    page.set_viewport_size({'width':1000,'height':800});assert_layout()
    page.set_viewport_size({'width':1440,'height':960})
    # All labels stay reachable without spilling onto adjacent commits.
    badge=page.locator('.branch-badges').first.get_by_role('button',name='Discuss branch main',exact=True)
    badge.click();expect(page.locator('.history-target-bar')).to_contain_text('Branch main')
    page.locator('.branch-filter summary').click()
    for name in [f'feature/long-review-branch-name-{i}' for i in range(12)]+['main','origin/review']:
        page.get_by_role('checkbox',name=name,exact=True).uncheck()
    expect(page.locator('.commit-row')).to_have_count(2)
    expect(page.locator('.branch-badge')).to_have_count(1)
    page.locator('.branch-filter summary').click();assert_layout()
    # Keep the keyboard-accessible commit button introduced with discussions.
    page.locator('.commit-select').first.focus();page.keyboard.press('Enter')
    expect(page.locator('.history-target-bar')).to_contain_text('Agent review')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_history_select_all_toggle_and_empty_selection(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    history_repo.__wrapped__(root)
    page.goto(url);page.locator('#history-open').click()
    expect(page.locator('.commit-row')).to_have_count(4)
    page.locator('.branch-filter summary').click()
    page.get_by_role('button',name='Deselect all branches',exact=True).click()
    expect(page.locator('.commit-row')).to_have_count(0)
    expect(page.locator('.branch-options input:checked')).to_have_count(0)
    expect(page.locator('.history-empty')).to_have_text('Choose a branch to see its history.')
    expect(page.locator('.history-more')).to_be_hidden()
    page.reload()
    expect(page.locator('.history-empty')).to_have_text('Choose a branch to see its history.')
    page.locator('.branch-filter summary').click()
    page.get_by_role('checkbox',name='agent/review',exact=True).check()
    expect(page.locator('.commit-row')).to_have_count(2)
    page.get_by_role('button',name='Select all branches',exact=True).click()
    expect(page.locator('.commit-row')).to_have_count(4)
    expect(page.locator('.branch-options input:checked')).to_have_count(2)
    # Selecting the last checkbox manually must also restore the all state.
    page.get_by_role('checkbox',name='main',exact=True).uncheck()
    expect(page.locator('.commit-row')).to_have_count(2)
    page.get_by_role('checkbox',name='main',exact=True).check()
    expect(page.locator('.commit-row')).to_have_count(4)
    expect(page.locator('.branch-filter summary')).to_have_text('All branches')
    page.get_by_role('button',name='Deselect all branches',exact=True).click()
    # A late response from selecting all must not undo a subsequent clear.
    pending=[]
    page.route('**/api/git/history?limit=100&*',lambda route:pending.append(route))
    with page.expect_request('**/api/git/history?limit=100&*'):
        page.get_by_role('button',name='Select all branches',exact=True).click()
    expect(page.get_by_role('button',name='Deselect all branches',exact=True)).to_be_visible()
    page.get_by_role('button',name='Deselect all branches',exact=True).click()
    assert len(pending)==1
    with page.expect_request_finished(lambda request:'/api/git/history?limit=100&' in request.url):
        pending.pop().fulfill(response=page.request.get(url+'/api/git/history',headers={'X-Looking-Glass-Token':ws.token}))
    page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    expect(page.locator('.commit-row')).to_have_count(0)
    expect(page.locator('.branch-options input:checked')).to_have_count(0)

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
