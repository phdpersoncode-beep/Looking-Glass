"""Review-mode behavior through the real editing and discussion controls."""
import os
import pytest
from test_requested_features import workspace_page, open_file
from test_markdown_discussions import select_text
pytestmark=[pytest.mark.browser,pytest.mark.skipif(not os.environ.get('LOOKING_GLASS_BROWSER'),reason='Set LOOKING_GLASS_BROWSER')]


def wait_saved(page):
    from playwright.sync_api import expect
    expect(page.locator('#review-status')).to_have_text('Review saved')
    expect(page.locator('#dirty')).to_have_text('')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_review_source_lifecycle_and_agent_changes(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    original='first = 1\r\nsecond = "🧠"\r\n'
    (root/'sample.py').write_bytes(original.encode())
    page.goto(url);open_file(page,'sample.py')
    page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    page.locator('.cm-content').click();page.keyboard.press('Control+Home');page.keyboard.press('End')
    page.keyboard.press('Shift+ArrowLeft');page.keyboard.insert_text('9')
    expect(page.locator('.review-deletion')).to_have_text('1')
    expect(page.locator('.review-human')).to_have_text('9')
    wait_saved(page)
    assert (root/'sample.py').read_bytes()==original.encode()
    draft=ws.reviews.read(ws.reviews.list()[0]['id'])
    draft=ws.reviews.update(draft['id'],draft['version'],[dict(start=len(draft['content']),end=len(draft['content']),insert='third = 3\r\n')],'Codex','agent')
    expect(page.locator('.review-agent')).to_have_text('third = 3')
    page.locator('#work-mode').select_option('edit')
    expect(page.locator('.review-deletion')).to_have_count(0)
    expect(page.locator('.cm-content')).to_contain_text('first = 1')
    assert 'third' not in page.locator('.cm-content').inner_text()
    page.locator('#work-mode').select_option('review')
    expect(page.locator('.review-agent')).to_have_text('third = 3')
    page.reload()
    expect(page.locator('#work-mode')).to_have_value('review')
    expect(page.locator('.review-human')).to_have_text('9')
    expect(page.locator('.review-agent')).to_have_text('third = 3')
    page.locator('#review-history').click()
    expect(page.locator('#review-events')).to_contain_text('Codex')
    page.locator('#review-history-dialog [data-close]').click()
    page.locator('#approve-review').click()
    expect(page.locator('#work-mode')).to_have_value('edit')
    expect(page.locator('.cm-content .review-agent')).to_have_count(0)
    assert (root/'sample.py').read_bytes()==draft['content'].encode()
    assert ws.reviews.list()==[]


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('mode',['live','preview'])
def test_review_markdown_tables_and_draft_comments(workspace_page,mode):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='# Report\n\n**old** passage.\n\n| Label | Value |\n| --- | --- |\n| width | 12 |\n\n```python\nx = 1\n```\n'
    (root/'report.md').write_text(text)
    page.goto(url);open_file(page,'report.md');page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    draft=ws.reviews.read(ws.reviews.list()[0]['id'])
    operations=[dict(start=text.index('12'),end=text.index('12')+2,insert='24'),dict(start=text.index('old'),end=text.index('old')+3,insert='new')]
    draft=ws.reviews.update(draft['id'],draft['version'],operations,'Codex','agent')
    expect(page.locator('.md-table .review-agent')).to_have_text('24')
    page.locator('#mode').select_option(mode)
    host='.md-table' if mode=='live' else '.markdown-preview'
    expect(page.locator(host+' .review-deletion')).to_have_text(['12'] if mode=='live' else ['old','12'])
    expect(page.locator(host+' .review-agent').filter(has_text='24')).to_be_visible()
    select_text(page,host+' tbody td:last-child .review-agent')
    page.locator('#annotate').click();expect(page.locator('#selected-quote')).to_have_text('24')
    page.locator('#comment-body').fill('Review value');page.locator('#comment-submit').click()
    expect(page.locator('.thread')).to_have_count(1)
    assert ws.threads('report.md')==[]
    assert ws.threads('report.md',review=draft['id'])[0]['quote']=='24'
    assert (root/'report.md').read_text()==text
    page.locator('#work-mode').select_option('edit')
    expect(page.locator('.thread')).to_have_count(0)
    page.locator('#work-mode').select_option('review')
    expect(page.locator('.thread')).to_have_count(1)
    page.locator('#approve-review').click();expect(page.locator('#work-mode')).to_have_value('edit')
    expect(page.locator('.thread')).to_have_count(1)
    assert ws.threads('report.md')[0]['quote']=='24'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_removed_passage_comments_editing_and_undo(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Original passage.\n')
    page.goto(url);open_file(page,'note.txt');page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    page.locator('.cm-content').click();page.keyboard.press('Control+Home');page.keyboard.press('Control+Shift+ArrowRight');page.keyboard.press('Backspace')
    wait_saved(page)
    ghost=page.locator('.cm-content .review-deletion');expect(ghost).to_have_text('Original ')
    ghost.focus();select_text(page,'.cm-content .review-deletion')
    expect(page.locator('#annotate')).to_be_enabled()
    page.locator('#annotate').click();expect(page.locator('#selected-quote')).to_have_text('Original')
    page.locator('#comment-body').fill('Keep this context');page.locator('#comment-submit').click()
    expect(page.locator('.thread')).to_have_count(1)
    page.get_by_role('button',name='Edit comment',exact=True).click()
    page.locator('#edit-comment-body').fill('Edited explanation');page.locator('#edit-comment-form button[type=submit]').click()
    expect(page.locator('.comment-markdown')).to_have_text('Edited explanation')
    draft=ws.reviews.read(ws.reviews.list()[0]['id'])
    t=ws.threads('note.txt',review=draft['id'])[0]
    assert t['anchor_kind']=='review_removed'
    assert ws.thread_context(t['id'])['context']['content']==t['render_anchor']['text']
    page.locator('.cm-content').click();page.keyboard.press('Control+z');wait_saved(page)
    expect(page.locator('.cm-content .review-deletion')).to_have_count(0)
    assert ws.reviews.read(draft['id'])['content']=='Original passage.\n'
    assert (root/'note.txt').read_text()=='Original passage.\n'


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_concurrent_review_drafts_have_explicit_recovery(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='first = 1\nsecond = 2\n';(root/'sample.py').write_text(text)
    page.goto(url);open_file(page,'sample.py');page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    draft=ws.reviews.read(ws.reviews.list()[0]['id'])
    # Freeze autosave delivery, then let the agent win the revision race.
    held=[];page.route('**/api/reviews/*',lambda route:held.append(route) if route.request.method=='PATCH' else route.continue_())
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text('human = 3\n')
    page.wait_for_timeout(600)
    assert held
    ws.reviews.update(draft['id'],draft['version'],[dict(start=0,end=0,insert='# Agent\n')],'Codex','agent')
    held[0].continue_();page.unroute('**/api/reviews/*')
    expect(page.locator('#review-conflict')).to_be_visible()
    expect(page.locator('.cm-content')).to_contain_text('human = 3')
    page.locator('#review-compare').click()
    expect(page.locator('#latest-review')).to_contain_text('# Agent')
    page.locator('#merged-review').fill('# Agent\n'+text+'human = 3\n')
    page.locator('#review-merge-form button[type=submit]').click()
    expect(page.locator('#review-merge-dialog')).not_to_be_visible()
    expect(page.locator('#review-conflict')).not_to_be_visible()
    expect(page.locator('.cm-content .review-agent')).to_contain_text('# Agent')
    expect(page.locator('.cm-content .review-human')).to_have_text('human = 3')
    assert (root/'sample.py').read_text()==text


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_approval_refuses_external_original_change(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    (root/'note.txt').write_text('Original')
    page.goto(url);open_file(page,'note.txt');page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    page.locator('.cm-content').click();page.keyboard.press('Control+End');page.keyboard.insert_text(' proposed');wait_saved(page)
    (root/'note.txt').write_text('External version')
    page.locator('#approve-review').click()
    expect(page.locator('#notice')).to_contain_text('changed on disk')
    assert (root/'note.txt').read_text()=='External version'
    expect(page.locator('#work-mode')).to_have_value('review')
    page.locator('#work-mode').select_option('edit')
    expect(page.locator('.cm-content')).to_have_text('External version')
    page.locator('#work-mode').select_option('review')
    expect(page.locator('.cm-content')).to_contain_text('proposed')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_review_html_rendering_source_and_runtime_comments(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='<h1>Report</h1><p>Old value</p><div id="runtime"></div><script>document.getElementById("runtime").textContent="Runtime passage"</script>'
    (root/'report.html').write_text(text)
    page.goto(url);open_file(page,'report.html');page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    draft=ws.reviews.read(ws.reviews.list()[0]['id'])
    draft=ws.reviews.update(draft['id'],draft['version'],[dict(start=text.index('Old'),end=text.index('Old')+3,insert='New')],'Codex','agent')
    frame=page.frame_locator('#html-preview')
    expect(frame.locator('p')).to_contain_text('New value')
    expect(frame.locator('.looking-glass-review-deletion')).to_have_text('Old')
    assert page.locator('#html-preview').content_frame.locator('p').evaluate("()=>CSS.highlights.has('looking-glass-review-agent')")
    frame.locator('#runtime').evaluate('''el=>{const range=document.createRange();range.selectNodeContents(el);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);document.dispatchEvent(new Event('selectionchange'));}''')
    expect(page.locator('#annotate')).to_be_enabled();page.locator('#annotate').click()
    page.locator('#comment-body').fill('Runtime note');page.locator('#comment-submit').click();expect(page.locator('.thread')).to_have_count(1)
    assert ws.threads('report.html',review=draft['id'])[0]['anchor_kind']=='rendered'
    assert ws.threads('report.html')==[]
    assert (root/'report.html').read_text()==text
    page.locator('#html-toggle').click();expect(page.locator('.cm-content .review-agent')).to_have_text('New')


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
@pytest.mark.parametrize('removed',['Old ','value','tail','value &amp; '])
def test_review_html_deletions_keep_character_order_and_source_anchors(workspace_page,removed):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='<p>Old value &amp; final tail</p>'
    (root/'report.html').write_text(text)
    page.goto(url);open_file(page,'report.html');page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    draft=ws.reviews.read(ws.reviews.list()[0]['id'])
    start=text.index(removed)
    draft=ws.reviews.update(draft['id'],draft['version'],[dict(start=start,end=start+len(removed),insert='')],'Codex','agent')
    frame=page.frame_locator('#html-preview')
    expect(frame.locator('.looking-glass-review-deletion')).to_have_text(removed)
    # Deleted source stays inert; entity spellings are displayed literally.
    expected='Old value & final tail' if '&amp;' not in removed else 'Old value &amp; final tail'
    expect(frame.locator('p')).to_have_text(expected)
    frame.locator('p').evaluate('''el=>{
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let node;
      while(walker.nextNode())if(!walker.currentNode.parentElement.closest('[data-looking-glass-overlay]')&&walker.currentNode.data.includes('final')){node=walker.currentNode;break;}
      const range=document.createRange(),at=node.data.indexOf('final');range.setStart(node,at);range.setEnd(node,at+5);
      const selection=getSelection();selection.removeAllRanges();selection.addRange(range);document.dispatchEvent(new Event('selectionchange'));
    }''')
    expect(page.locator('#annotate')).to_be_enabled();page.locator('#annotate').click()
    page.locator('#comment-body').fill('Still anchored after splitting');page.locator('#comment-submit').click()
    expect(page.locator('.thread')).to_have_count(1)
    thread=ws.threads('report.html',review=draft['id'])[0]
    assert thread['anchor_kind']=='source' and thread['quote']=='final'
    assert thread['start']==draft['content'].index('final')
    page.set_viewport_size(dict(width=1100,height=800))
    expect(frame.locator('p')).to_have_text(expected)
    assert (root/'report.html').read_text()==text


@pytest.mark.parametrize('workspace_page',['chromium','firefox'],indirect=True)
def test_review_html_multiple_deletions_preserve_mapped_selection(workspace_page):
    from playwright.sync_api import expect
    root,page,url,ws=workspace_page
    text='<p>🧠 One first two second three</p>'
    (root/'report.html').write_text(text)
    page.goto(url);open_file(page,'report.html');page.locator('#work-mode').select_option('review')
    expect(page.locator('#approve-review')).to_be_visible()
    draft=ws.reviews.read(ws.reviews.list()[0]['id'])
    operations=[dict(start=text.index(quote),end=text.index(quote)+len(quote),insert='')
                for quote in ('second ','first ')]
    draft=ws.reviews.update(draft['id'],draft['version'],operations,'Codex','agent')
    frame=page.frame_locator('#html-preview')
    expect(frame.locator('.looking-glass-review-deletion')).to_have_text(['first ','second '])
    expect(frame.locator('p')).to_have_text('🧠 One first two second three')
    frame.locator('p').evaluate('''el=>{const range=document.createRange();range.selectNodeContents(el);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);document.dispatchEvent(new Event('selectionchange'));}''')
    expect(page.locator('#annotate')).to_be_enabled();page.locator('#annotate').click()
    expect(page.locator('#selected-quote')).to_have_text('🧠 One two three')
    page.locator('#comment-body').fill('Accepted source across both deletions');page.locator('#comment-submit').click()
    expect(page.locator('.thread')).to_have_count(1)
    thread=ws.threads('report.html',review=draft['id'])[0]
    assert thread['anchor_kind']=='source' and thread['quote']=='🧠 One two three'
    assert thread['start']==3
    assert (root/'report.html').read_text()==text
